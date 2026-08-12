from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA


class BreezySource:
    source = "breezy"

    def list_postings(self, token: str, **kwargs) -> list[PostingStub]:
        host = kwargs.get("host") or f"{token}.breezy.hr"
        resp = polite_get(f"https://{host}/json", headers={"User-Agent": UA})
        resp.raise_for_status()
        data = resp.json()

        postings: list[PostingStub] = []
        seen: set[str] = set()
        for item in data:
            external_id = item.get("id") or item.get("friendly_id")
            if not external_id or external_id in seen:
                continue
            seen.add(external_id)
            location = item.get("location") or {}
            postings.append(
                PostingStub(
                    source=self.source,
                    external_id=external_id,
                    title=item.get("name"),
                    url=item.get("url"),
                    location=location.get("name"),
                    updated_at=item.get("published_date"),
                    comp=item.get("salary"),
                )
            )
        return postings
