import json
import boto3
import time
import logging
from typing import Dict, Any, Optional, Union
import os
import dotenv
from botocore.config import Config

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(message)s",
)


class BedrockAnthropicLLM:
    """
    A class for interacting with AWS Bedrock LLMs.
    Initializes the Bedrock client once and reuses it across multiple invocations.
    """
    
    def __init__(self, region_name: str = 'us-east-1'):
        """
        Initialize the BedrockLLM client.
        
        Args:
            region_name: AWS region name (optional, uses 'us-east-1' by default)
        """

        app_env = os.getenv("APP_ENV", "duplo")
        logger.info(f"Initializing Bedrock client for APP_ENV: {app_env}")

        config = Config(
            read_timeout=1000
        )

        if app_env == "local":
            self.bedrock_runtime = boto3.client(
                'bedrock-runtime', 
                region_name=region_name,
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
                config=config,
                verify=True   
                        )
        else:
            self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=region_name, config=config)
    
    def invoke(
        self,
        messages: list,
        model_id: str,
        max_tokens: int = 1000,
        temperature: float = 0.0,
        top_p: float = 0.9,
        top_k: Optional[int] = None,
        stop_sequences: Optional[list] = None,
        latency: str = "standard",
        system_prompt: Optional[str] = None,
        tools: Optional[list] = None,
        additional_params: Optional[Dict[str, Any]] = None,
        tool_choice: Optional[dict] = None,
        return_raw_api_response: bool = False
    ) -> Union[str, Dict[str, Any]]:
        """
        Invoke an AWS Bedrock LLM with the given prompt and parameters.
        
        Args:
            messages: The messages to send to the model
            model_id: The Bedrock model ID (e.g., 'anthropic.claude-3-5-sonnet-20240620-v1:0')
            max_tokens: Maximum number of tokens to generate
            temperature: Controls randomness (0-1)
            top_p: Controls diversity via nucleus sampling (0-1)
            top_k: Limits vocabulary to top K options (model-specific)
            stop_sequences: List of strings that will stop generation when encountered
            latency: handled at API call level via performanceConfigLatency header.
            additional_params: Any additional model-specific parameters
            
        Returns:
            The text response from the LLM
        """

        if "anthropic" not in model_id.lower():
            raise ValueError(f"Unsupported model: {model_id}. Currently only Anthropic/Claude models are supported.")

        logger.info("Messages in LLM API Call: %s", messages)

        messages = self.normalize_message_roles(messages)
        # Prepare request body based on model provider
        request_body = self._prepare_request_body(
            messages, model_id, max_tokens, temperature, top_p, top_k, stop_sequences, system_prompt, tools, tool_choice
        )
        
        # Override or add any additional parameters
        if additional_params:
            request_body.update(additional_params)

        logger.info(
            "Invoking model %s (latency=%s)",
            model_id,
            latency,
        )
        start_time = time.perf_counter()

        
        # Invoke the model
        #TODO: Update to use the converse bedrock API, so it's easier to switch models.
        response = self.bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json",
            performanceConfigLatency=latency,
        )
        
        elapsed = time.perf_counter() - start_time
        logger.info("Model %s call completed in %.2f seconds", model_id, elapsed)
        
        # Parse and return the response
        response_body = json.loads(response['body'].read().decode('utf-8'))

        logger.info("LLM Response body: %s", response_body)

        if return_raw_api_response:
            return response_body
        else:
            return self._extract_response(response_body, model_id, tool_choice)
    
    def _prepare_request_body(
        self,
        messages: list,
        model_id: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        top_k: Optional[int],
        stop_sequences: Optional[list],
        system_prompt: Optional[str],
        tools: Optional[list],
        tool_choice: Optional[dict],
    ) -> Dict[str, Any]:
        """
        Prepare the appropriate request body based on the model provider.
        
        Args:
            prompt: The text prompt to send to the model
            model_id: The Bedrock model ID
            max_tokens: Maximum number of tokens to generate
            temperature: Controls randomness (0-1)
            top_p: Controls diversity via nucleus sampling (0-1)
            top_k: Limits vocabulary to top K options (model-specific)
            stop_sequences: List of strings that will stop generation
            
        Returns:
            The formatted request body as a dictionary
            
        Raises:
            ValueError: If the model is not an Anthropic/Claude model
        """
        # Format for Claude models
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "messages": messages,
        }

        if system_prompt:
            request_body["system"] = system_prompt

        if tools:
            request_body["tools"] = tools

        if tool_choice:
            request_body["tool_choice"] = tool_choice
        
        # Add Claude 3.5 Haiku optimized parameters if available
        if "claude-3-5-haiku" in model_id.lower() and top_k is not None:
            request_body["top_k"] = top_k
            
        if stop_sequences:
            request_body["stop_sequences"] = stop_sequences
        
        # Latency config is passed as a header parameter in invoke_model, not in request body.
        
        return request_body
    
    def normalize_message_roles(self, messages: list) -> list:
        """Normalize message roles by merging consecutive messages with the same role.

        Bedrock requires that roles strictly alternate between 'user' and 'assistant'.
        If two or more adjacent messages have the same role (either 'user' or 'assistant'),
        we merge their content fields into one message and remove the extras.

        Bedrock does not accept empty messages, so remove empty messages for now..
        
        This function processes the entire message list recursively until no more
        merges are possible, ensuring the final list has proper role alternation.
        """
        if not messages:
            return messages

        # Remove empty messages
        messages = [msg for msg in messages if msg.get("content", "").strip()]
            
        # Base case: single message or already normalized list
        if len(messages) == 1:
            return messages.copy()

        # First pass: merge adjacent messages with the same role
        merged = []
        i = 0
        while i < len(messages):
            current = messages[i].copy()
            merged.append(current)
            
            # Look ahead for consecutive messages with the same role
            j = i + 1
            while j < len(messages) and messages[j].get("role") == current.get("role"):
                # Merge content from the next message into the current one
                self._merge_message_content(current, messages[j])
                j += 1
                
            # Skip all messages that were merged
            i = j
            
        # Recursive case: if we performed any merges, run again to ensure complete normalization
        if len(merged) < len(messages):
            return self.normalize_message_roles(merged)
        else:
            return merged

    def _merge_message_content(self, target_msg: dict, source_msg: dict) -> None:
        """Helper method to merge content from source message into target message.
        
        Handles different content formats (string, list) appropriately.
        """
        prev_content = target_msg.get("content", "")
        curr_content = source_msg.get("content", "")

        # Handle the different content formats: str + str, list + list, and mixed
        if isinstance(prev_content, list) and isinstance(curr_content, list):
            target_msg["content"] = prev_content + curr_content
        elif isinstance(prev_content, list):
            target_msg["content"] = prev_content + [curr_content]
        elif isinstance(curr_content, list):
            target_msg["content"] = [prev_content] + curr_content
        else:  # both strings (or fall-back to str)
            target_msg["content"] = f"{prev_content}\n{curr_content}"

    def _extract_response(self, response_body: Dict[str, Any], model_id: str, tool_choice: Optional[Dict[str, Any]] = None) -> str:
        """
        Extract the generated text from the response based on model provider.
        
        Args:
            response_body: The response body as a dictionary
            model_id: The Bedrock model ID
        
        Returns:
            The extracted text response as a string
            
        Raises:
            ValueError: If the model is not an Anthropic/Claude model
        """

        logger.info(f"Response body: {response_body}")

        # if response_body["stop_reason"] == "tool_use":
        if tool_choice and tool_choice["type"] == "tool":
            output = response_body["content"][0]["input"]
            return output
        else:
            return response_body["content"][0]["text"]