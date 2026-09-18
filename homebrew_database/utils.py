import os
import urllib.parse

def relative_to_absolute_url(url: str | None) -> str | None:
    if url is None:
        return None
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc:
        return url
    if not os.environ.get("CI"):
        return url
    
    owner,repo = os.environ["GITHUB_REPOSITORY"].split("/")
    return str(urllib.parse.urljoin(f"https://{owner}.github.io/{repo}", url))
