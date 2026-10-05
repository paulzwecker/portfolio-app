"""Consensus source continuity is explicit and provider-specific."""

from portfolio_api.domain.models import ConsensusEstimateProviderMapping


def select_consensus_source(
    mappings: list[ConsensusEstimateProviderMapping],
) -> tuple[ConsensusEstimateProviderMapping | None, str]:
    """Select one provider stream without cross-provider period filling or blending."""
    primary = [item for item in mappings if item.role == "PRIMARY"]
    if primary:
        return max(primary, key=lambda item: item.effective_from), "PRIMARY_SELECTED"
    fallbacks = [item for item in mappings if item.role == "FALLBACK"]
    if not fallbacks:
        return None, "NO_MAPPING"
    priority = min(item.priority for item in fallbacks)
    preferred = [item for item in fallbacks if item.priority == priority]
    if len(preferred) != 1:
        return None, "AMBIGUOUS_FALLBACK"
    return preferred[0], "FALLBACK_SELECTED"
