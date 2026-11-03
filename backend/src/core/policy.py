import uuid

from src.domain.entities.policy import FairnessPolicy, FairnessPolicyUpdate
from src.domain.interfaces.repositories.policy import FairnessPolicyRepositoryInterface
from src.domain.interfaces.uow import UnitOfWorkFactory
from src.shared.logging import get_logger

logger = get_logger(__name__)


class FairnessPolicyService:
    def __init__(self, policies: FairnessPolicyRepositoryInterface, uow: UnitOfWorkFactory) -> None:
        self._policies = policies
        self._uow = uow

    async def get_for_seller(self, seller_id: uuid.UUID) -> FairnessPolicy | None:
        return await self._policies.get_by_seller(seller_id)

    async def get_policy_text(self, seller_id: uuid.UUID | None) -> str:
        if seller_id is None:
            return ""
        policy = await self._policies.get_by_seller(seller_id)
        return policy.get("rules_text", "") if policy else ""

    async def set_policy(self, seller_id: uuid.UUID, fields: FairnessPolicyUpdate) -> FairnessPolicy:
        async with self._uow():
            policy = await self._policies.upsert(seller_id=seller_id, fields=fields)
        logger.info("Fairness policy set", extra={"event": "policy.set", "seller_id": str(seller_id)})
        return policy

    @staticmethod
    def as_guardrail_dict(policy: FairnessPolicy | None) -> dict:
        """Extract the numeric guardrail overrides the executor honours."""
        if not policy:
            return {}
        return {
            k: policy.get(k)
            for k in ("confidence_threshold", "human_in_loop_amount", "partial_refund_ceiling", "auto_accept_max", "always_refund_under")
            if policy.get(k) is not None
        }
