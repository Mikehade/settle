"""The single DI container. Everything is built here and injected.

Sections are ordered so providers are defined before they are used.
`manage.py startapp` inserts new lines at the `# [kit:...]` markers.
"""
from dependency_injector import containers, providers

from src.config import get_settings
from src.core.health import HealthService
from src.infrastructure.db.session import Database
from src.infrastructure.db.uow import UnitOfWork
from src.core.auth import AuthService
from src.core.users import UserService
from src.infrastructure.repositories.users import SqlUserRepository
from src.infrastructure.services.password_hasher import Argon2PasswordHasher
from src.infrastructure.services.token_service import JwtTokenService
from src.core.audit import AuditService
from src.core.disputes import DisputeService
from src.core.mediation import MediationService
from src.core.policy import FairnessPolicyService
from src.domain.core.agents.mediator import MediatorAgent
from src.domain.core.tools.evidence_tools import EvidenceTools
from src.domain.core.tools.propose_tools import ProposalTools
from src.infrastructure.clients.paypal_http import PayPalHttpClient
from src.infrastructure.language_models.bedrock import BedrockModel
from src.infrastructure.repositories.audit import SqlAuditRepository
from src.infrastructure.repositories.disputes import SqlDisputeRepository
from src.infrastructure.repositories.policy import SqlFairnessPolicyRepository
from src.infrastructure.services.dispute_source import DisputeSource
from src.infrastructure.services.executor import PayPalExecutor
from src.infrastructure.services.paypal_client import PayPalClient
# [kit:imports]


class Container(containers.DeclarativeContainer):
    config = providers.Singleton(get_settings)

    # ---- Resources ---------------------------------------------------------
    database = providers.Singleton(
        Database,
        url=config.provided.DATABASE_URL,
        echo=config.provided.DB_ECHO,
        pool_size=config.provided.DB_POOL_SIZE,
        max_overflow=config.provided.DB_MAX_OVERFLOW,
    )

    # ---- Infra services ----------------------------------------------------
    password_hasher = providers.Singleton(Argon2PasswordHasher)
    token_service = providers.Singleton(
        JwtTokenService,
        secret_key=config.provided.SECRET_KEY,
        algorithm=config.provided.JWT_ALGORITHM,
        access_ttl_seconds=config.provided.ACCESS_TOKEN_TTL_SECONDS,
    )
    # ---- PayPal -----------------------------------------------------------
    paypal_http_client = providers.Singleton(
        PayPalHttpClient,
        client_id=config.provided.PAYPAL_CLIENT_ID,
        client_secret=config.provided.PAYPAL_CLIENT_SECRET,
        base_url=config.provided.PAYPAL_BASE_URL,
        timeout=config.provided.PAYPAL_HTTP_TIMEOUT,
    )
    paypal_client = providers.Singleton(PayPalClient, http=paypal_http_client)
    dispute_source = providers.Singleton(
        DisputeSource, paypal_client=paypal_client, mode=config.provided.DISPUTE_SOURCE_MODE
    )
    paypal_executor = providers.Singleton(
        PayPalExecutor,
        paypal_client=paypal_client,
        confidence_threshold=config.provided.GUARDRAIL_CONFIDENCE_THRESHOLD,
        human_in_loop_amount=config.provided.GUARDRAIL_HUMAN_IN_LOOP_AMOUNT,
        partial_refund_ceiling=config.provided.GUARDRAIL_PARTIAL_REFUND_CEILING,
    )

    # ---- AI (a fresh model + agent per mediation run) ---------------------
    bedrock_model = providers.Factory(
        BedrockModel,
        aws_access_key=config.provided.AWS_ACCESS_KEY_ID,
        aws_secret_key=config.provided.AWS_SECRET_ACCESS_KEY,
        model_id=config.provided.BEDROCK_MODEL_ID,
        region_name=config.provided.AWS_REGION,
        temperature=config.provided.BEDROCK_TEMPERATURE,
    )
    proposal_tools = providers.Factory(ProposalTools)
    evidence_tools = providers.Factory(EvidenceTools)
    mediator_agent = providers.Factory(
        MediatorAgent,
        llm_model=bedrock_model,
        proposal_tools=proposal_tools,
        evidence_tools=evidence_tools,
        graph=config.provided.MEDIATION_ENGINE_GRAPH,
    )
    # [kit:infra]

    # ---- Unit of work ------------------------------------------------------
    uow = providers.Factory(UnitOfWork, db=database)

    # ---- Repositories ------------------------------------------------------
    user_repository = providers.Singleton(SqlUserRepository, db=database)
    dispute_repository = providers.Singleton(SqlDisputeRepository, db=database)
    policy_repository = providers.Singleton(SqlFairnessPolicyRepository, db=database)
    audit_repository = providers.Singleton(SqlAuditRepository, db=database)
    # [kit:repositories]

    # ---- Core --------------------------------------------------------------
    health_service = providers.Singleton(HealthService, checks=providers.List(database))
    user_service = providers.Singleton(
        UserService, users=user_repository, hasher=password_hasher, uow=uow.provider
    )
    auth_service = providers.Singleton(
        AuthService, users=user_repository, hasher=password_hasher, tokens=token_service
    )
    dispute_service = providers.Singleton(DisputeService, disputes=dispute_repository, uow=uow.provider)
    policy_service = providers.Singleton(FairnessPolicyService, policies=policy_repository, uow=uow.provider)
    audit_service = providers.Singleton(AuditService, audit=audit_repository, uow=uow.provider)
    mediation_service = providers.Singleton(
        MediationService,
        dispute_source=dispute_source,
        executor=paypal_executor,
        mediator_factory=mediator_agent.provider,
        dispute_service=dispute_service,
        policy_service=policy_service,
        audit_service=audit_service,
    )
    # [kit:core]
