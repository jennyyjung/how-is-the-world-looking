from dataclasses import dataclass


@dataclass(frozen=True)
class SourceConfig:
    key: str
    name: str
    source_type: str
    description: str


SOURCE_REGISTRY: dict[str, SourceConfig] = {
    "github_trending_stars": SourceConfig(
        key="github_trending_stars",
        name="GitHub Trending/Stars",
        source_type="api",
        description="Trending repositories discovered from GitHub repository search sorted by stars.",
    ),
    "hacker_news": SourceConfig(
        key="hacker_news",
        name="Hacker News",
        source_type="api",
        description="Top stories from Hacker News Firebase API.",
    ),
    "google_news_api": SourceConfig(
        key="google_news_api",
        name="Google News API",
        source_type="api",
        description="Google News-compatible API feed for latest technology and AI headlines.",
    ),
}
