from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA


class RecruiteeSource:
    source = "recruitee"

    def list_postings(self, token: str, **kwargs) -> list[PostingStub]:
        url = f"https://{token}.recruitee.com/api/offers/"
        resp = polite_get(url, headers={"User-Agent": UA})
        resp.raise_for_status()
        data = resp.json()

        postings = []
        seen = set()
        for offer in data.get("offers", []):
            external_id = str(offer.get("id"))
            if not external_id or external_id in seen:
                continue
            seen.add(external_id)

            location = offer.get("location") or None
            if not location:
                loc_parts = [p for p in [offer.get("city"), offer.get("state_name"), offer.get("country")] if p]
                location = ", ".join(loc_parts) or None

            postings.append(PostingStub(
                source=self.source,
                external_id=external_id,
                title=offer.get("title"),
                url=offer.get("careers_url") or f"https://{token}.recruitee.com/o/{offer.get('slug')}",
                location=location,
                updated_at=offer.get("updated_at"),
                comp=None,
            ))
        return postings
