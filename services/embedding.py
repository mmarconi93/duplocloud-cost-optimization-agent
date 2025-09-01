import boto3
import os
import logging
from typing import List
from langchain_community.embeddings import BedrockEmbeddings
import dotenv

logger = logging.getLogger(__name__)

class EmbeddingProvider:
    """Factory class to create embedding models."""
    
    @staticmethod
    def create(provider: str, **kwargs):
        """
        Create an embedding model.
        
        Args:
            provider: Provider name (e.g. 'bedrock')
            **kwargs: Additional arguments for the provider
            
        Returns:
            Embedding model instance
        """
        if provider.lower() == "bedrock":
            return BedrockEmbeddingProvider(**kwargs)
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")

class BedrockEmbeddingProvider:
    """Embedding provider using AWS Bedrock."""
    
    def __init__(
            self,
            model_id: str = "amazon.titan-embed-text-v1",
            region_name: str = "us-east-1",
            batch_size: int = 100,
            **kwargs
        ):
        """
        Initialize Bedrock embedding provider.
        
        Args:
            model_id: Model ID to use for embeddings
            region_name: AWS region for Bedrock
            batch_size: Number of texts to embed in a single batch
            **kwargs: Additional arguments for the Bedrock client
        """
        self.model_id = model_id
        self.region_name = region_name
        self.batch_size = batch_size
        
        # Get AWS credentials from environment variables
        aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        aws_session_token = os.environ.get("AWS_SESSION_TOKEN")
        
        # Create Bedrock client with explicit credentials
        # In local mode, always use credentials from environment variables
        # In prod mode, allow boto3 to use the default credential provider chain
        app_env = os.getenv("APP_ENV", "duplo")
        if app_env.lower() == "local":
            if not aws_access_key_id or not aws_secret_access_key:
                logger.error("AWS credentials not found in environment variables. Please make sure .env file is properly configured.")
                raise ValueError("AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env file.")
                
            logger.info("Using AWS credentials from environment variables for Bedrock (local mode)")
            self.bedrock_client = boto3.client(
                service_name="bedrock-runtime",
                region_name=region_name,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                aws_session_token=aws_session_token,
                **kwargs
            )
        else:
            # In prod mode, fall back to default credential provider chain
            logger.info("Using default AWS credential provider chain for Bedrock (prod mode)")
            self.bedrock_client = boto3.client(
                service_name="bedrock-runtime",
                region_name=region_name,
                **kwargs
            )
        
        # Initialize LangChain embedding model
        self.embedding_model = BedrockEmbeddings(
            client=self.bedrock_client,
            model_id=model_id
        )
        
        logger.info(f"Initialized Bedrock embedding provider with model {model_id}")
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of documents.
        
        Args:
            texts: List of document texts to embed
            
        Returns:
            List of embedding vectors
        """
        try:
            embeddings = []
            
            # Process in batches to avoid overloading the API
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                logger.info(f"Embedding batch {i//self.batch_size + 1} with {len(batch)} texts")
                batch_embeddings = self.embedding_model.embed_documents(batch)
                embeddings.extend(batch_embeddings)
            
            return embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise
    
    def embed_query(self, text: str) -> List[float]:
        """
        Generate embedding for a single query text.
        
        Args:
            text: Query text to embed
            
        Returns:
            Embedding vector
        """
        try:
            return self.embedding_model.embed_query(text)
        except Exception as e:
            logger.error(f"Error generating query embedding: {str(e)}")
            raise


#Example usage
if __name__ == "__main__":
    dotenv.load_dotenv(override=True)

    model_id = "cohere.embed-english-v3"
    embedding_provider = BedrockEmbeddingProvider(model_id=model_id)
    texts = ["Hello world", "Hello universe"]
    embeddings = embedding_provider.embed_documents(texts)
    print("Texts embeddings: ", embeddings)

    query = "Hello"
    query_embedding = embedding_provider.embed_query(query)
    print("Query embedding: ", query_embedding)