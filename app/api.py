"""API server module.

This module initializes and configures the FastAPI application,
including routers, middleware, and startup/shutdown events.

The API server provides endpoints for agent execution and management.
"""

import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.admin import (
    admin_router,
    admin_router_readonly,
    agent_generator_router,
    credit_router,
    credit_router_readonly,
    health_router,
    metadata_router_readonly,
    schema_router_readonly,
    user_router,
    user_router_readonly,
)
from app.entrypoints.agent_api import router_ro as agent_api_ro
from app.entrypoints.agent_api import router_rw as agent_api_rw
from app.entrypoints.openai_compatible import openai_router
from app.entrypoints.web import chat_router, chat_router_readonly
from app.services.twitter.oauth2 import router as twitter_oauth2_router
from app.services.twitter.oauth2_callback import router as twitter_callback_router
from intentkit.config.config import config
from intentkit.core.api import core_router
from intentkit.models.agent import AgentTable
from intentkit.models.db import get_session, init_db
from intentkit.models.redis import init_redis
from intentkit.utils.error import (
    IntentKitAPIError,
    http_exception_handler,
    intentkit_api_error_handler,
    intentkit_other_error_handler,
    request_validation_exception_handler,
)

# init logger
logger = logging.getLogger(__name__)

if config.sentry_dsn:
    sentry_sdk.init(
        dsn=config.sentry_dsn,
        sample_rate=config.sentry_sample_rate,
        traces_sample_rate=config.sentry_traces_sample_rate,
        profiles_sample_rate=config.sentry_profiles_sample_rate,
        environment=config.env,
        release=config.release,
        server_name="intent-api",
    )

# Create Agent API sub-application
agent_app = FastAPI(
    title="IntentKit Agent API",
    summary="Agent API with OpenAI-compatible endpoints",
    version=config.release,
    contact={
        "name": "IntentKit Team",
        "url": "https://github.com/crestalnetwork/intentkit",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# Add exception handlers to the Agent API sub-application
agent_app.exception_handler(IntentKitAPIError)(intentkit_api_error_handler)
agent_app.exception_handler(RequestValidationError)(
    request_validation_exception_handler
)
agent_app.exception_handler(StarletteHTTPException)(http_exception_handler)
agent_app.exception_handler(Exception)(intentkit_other_error_handler)

# Add CORS middleware to the Agent API sub-application
agent_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Add routers to the Agent API sub-application
agent_app.include_router(agent_api_rw)
agent_app.include_router(agent_api_ro)
agent_app.include_router(openai_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle.

    This context manager:
    1. Initializes database connection
    2. Performs any necessary startup tasks
    3. Handles graceful shutdown

    Args:
        app: FastAPI application instance
    """
    # Initialize database
    await init_db(**config.db)

    # Initialize Redis if configured
    if config.redis_host:
        await init_redis(
            host=config.redis_host,
            port=config.redis_port,
        )

    # Create example agent if no agents exist
    await create_example_agent()

    logger.info("API server start")
    yield
    # Clean up will run after the API server shutdown
    logger.info("Cleaning up and shutdown...")


app = FastAPI(
    lifespan=lifespan,
    title="IntentKit API",
    summary="IntentKit API Documentation",
    version=config.release,
    contact={
        "name": "IntentKit Team",
        "url": "https://github.com/crestalnetwork/intentkit",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)


app.exception_handler(IntentKitAPIError)(intentkit_api_error_handler)
app.exception_handler(RequestValidationError)(request_validation_exception_handler)
app.exception_handler(StarletteHTTPException)(http_exception_handler)
app.exception_handler(Exception)(intentkit_other_error_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Mount the Agent API sub-application
app.mount("/v1", agent_app)

app.include_router(chat_router)
app.include_router(chat_router_readonly)
app.include_router(admin_router)
app.include_router(admin_router_readonly)
app.include_router(metadata_router_readonly)
app.include_router(credit_router)
app.include_router(credit_router_readonly)
app.include_router(schema_router_readonly)
app.include_router(user_router)
app.include_router(user_router_readonly)
app.include_router(core_router)
app.include_router(twitter_callback_router)
app.include_router(twitter_oauth2_router)
app.include_router(health_router)
app.include_router(agent_generator_router)


async def create_example_agent() -> None:
    """Create an example agent if no agents exist in the database.

    Creates an agent with ID 'example' and basic configuration if the agents table is empty.
    The agent is configured with the 'common' skill with 'current_time' state set to 'public'.
    """
    try:
        async with get_session() as session:
            # Check if any agents exist - more efficient count query
            result = await session.execute(
                select(select(AgentTable.id).limit(1).exists().label("exists"))
            )
            if result.scalar():
                logger.debug("Example agent not created: agents already exist")
                return  # Agents exist, nothing to do

            # Create example agent
            example_agent = AgentTable(
                id="example",
                name="Example",
                owner="intentkit",
                skills={
                    "system": {
                        "states": {"read_agent_api_key": "private"},
                        "enabled": True,
                    }
                },
            )

            session.add(example_agent)
            await session.commit()
            logger.info("Created example agent with ID 'example'")
    except Exception as e:
        logger.error(f"Failed to create example agent: {str(e)}")
        # Don't re-raise the exception to avoid blocking server startup
