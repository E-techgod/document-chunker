from document_chunker.schemas import ChunkingConfig

CHUNKING_STRATEGIES = {
    "v1.0": {
        "label": "Character chunking with overlap",
        "config": ChunkingConfig(
            max_chunk_size=1000,
            overlap_size=100,
            chunking_strategy="characters",
            propagate_context=False,
        ),
    },
    "v2.1": {
        "label": "Structural chunking with no context carry",
        "config": ChunkingConfig(
            max_chunk_size=1000,
            overlap_size=0,
            chunking_strategy="structural",
            propagate_context=False,
        ),
    },
    "v2.2": {
        "label": "Structural chunking with context carry",
        "config": ChunkingConfig(
            max_chunk_size=1000,
            overlap_size=0,
            chunking_strategy="structural",
            propagate_context=True,
        ),
    },
}

def get_chunking_strategy(strategy_name: str) -> tuple[str, ChunkingConfig]:
    strategy = CHUNKING_STRATEGIES.get(strategy_name)
    if strategy is None:
        valid_strategies = ", ".join(CHUNKING_STRATEGIES)
        raise ValueError(
            f"Unsupported chunking strategy: {strategy_name}. Choose one of: {valid_strategies}"
        )
    return strategy["label"], strategy["config"]


def describe_chunking(config: ChunkingConfig) -> str:
    if config.chunking_strategy == "characters":
        return "overlapping character chunks"
    if config.propagate_context:
        return "structural chunks with context carry"
    return "structural chunks with no context carry"