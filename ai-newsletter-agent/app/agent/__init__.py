# Expose the compiled graph as the main entry point for the module
from .graph import workflow_app

__all__ = ["workflow_app"]
