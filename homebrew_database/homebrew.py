from dataclasses import dataclass, field
import datetime
import os
import json
import glob
import logging

from homebrew_database.utils import relative_to_absolute_url


class HomebrewProcessingException(Exception):
    pass


@dataclass
class Release:
    tag: str
    url: str
    published_at: datetime.date
    sha256: str | None = None
    eboot_md5: str | None = None
    changelog: str | None = None
    size: int | None = None

    def __gt__(self, other: 'Release') -> bool:
        return self.published_at > other.published_at

    def to_dict(self) -> dict:
        return_dict = {
            "tag": self.tag,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "size": self.size,
        }
        if self.sha256 is not None:
            return_dict["sha256"] = self.sha256
        if self.eboot_md5 is not None:
            return_dict["eboot_md5"] = self.eboot_md5
        if self.changelog is not None:
            return_dict["changelog"] = self.changelog
        if self.size is not None:
            return_dict["size"] = self.size
        return return_dict


@dataclass
class Homebrew:
    name: str
    id: str
    summary: str
    author: str
    screenshots: list[str]
    ai_used: bool
    requires_additional_files: bool
    category: str
    description: str | None = None
    website: str | None = None
    source: str | None = None
    license: str | None = None
    releases: list[Release] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    icon: str = None

    def __gt__(self, other: 'Homebrew') -> bool:
        self_last_release = self.get_last_release()
        other_last_release = other.get_last_release()
        if other_last_release is None:
            return self
        if self_last_release is None:
            return other
        return self.get_last_release() > other.get_last_release()

    def get_last_release(self) -> Release | None:
        if len(self.releases) == 0:
            return None
        return sorted(self.releases, reverse=True)[0]

    def to_dict(self) -> dict:
        return_dict = {
            "name": self.name,
            "id": self.id,
            "summary": self.summary,
            "author": self.author,
            "ai_used": self.ai_used,
            "requires_additional_files": self.requires_additional_files,
            "category": self.category,
            "releases": [],
            "tags": self.tags,
            "media": {
                "screenshots": self.screenshots,
            },
        }

        if self.description is not None:
            return_dict["description"] = self.description
        if self.website is not None:
            return_dict["website"] = self.website
        if self.source is not None:
            return_dict["source"] = self.source
        if self.license is not None:
            return_dict["license"] = self.license
        if self.icon is not None:
            return_dict["media"]["icon"] = self.icon
        if self.languages is not None:
            return_dict["languages"] = self.languages
        
        self.releases.sort(reverse=True)
        for release in self.releases:
            return_dict["releases"].append(release.to_dict())

        return return_dict


def get_homebrew_from_json_data(id: str, data: dict) -> Homebrew:
    if not data:
        raise HomebrewProcessingException(f"No data to read found in {id}")

    try:
        releases = []
        for release_data in data["releases"]:
            releases.append(
                Release(
                    tag=release_data["tag"],
                    url=release_data["url"],
                    changelog=release_data.get("changelog", None),
                    published_at=datetime.date.fromisoformat(release_data["published_at"]),
                    sha256=release_data.get("sha256", None),
                    eboot_md5=release_data.get("eboot_md5", None),
                    size=release_data.get("size", None),
                )
            )

        screenshots = []
        for screenshot in data["media"].get("screenshots", []):
            screenshots.append(relative_to_absolute_url(screenshot))

        homebrew = Homebrew(
          name=data["name"],
          id=id,
          summary=data["summary"],
          author=data["author"],
          screenshots=screenshots,
          ai_used=data["ai_used"],
          requires_additional_files=data["requires_additional_files"],
          category=data["category"],
          description=data.get("description", None),
          website=data.get("website", None),
          source=data.get("source", None),
          license=data.get("license", None),
          releases=releases,
          tags=data.get("tags", list()),
          icon=relative_to_absolute_url(data["media"].get("icon", None)),
          languages=data.get("languages", list()),
        )
    except (KeyError, ValueError) as e:
        raise HomebrewProcessingException(f"Could not process json data for {id}") from e

    return homebrew


def get_homebrew_list(data_dir: str) -> list[Homebrew]:
    homebrew_list = []
    failed_to_load = []
    for file_name in glob.iglob(f"{data_dir}/**", recursive=True):
        if not file_name.endswith(".json"):
            continue
        if not os.path.isfile(file_name):
            continue
        with open(file_name, "r") as fd:
            try:
                data = json.loads(fd.read())
                id = os.path.splitext(os.path.basename(file_name))[0]
                homebrew = get_homebrew_from_json_data(id=id, data=data)
                homebrew_list.append(homebrew)
            except (json.JSONDecodeError, TypeError, HomebrewProcessingException):
                logging.error("Could no load the content of %s as json", file_name, exc_info=True)
                failed_to_load.append(file_name)
                continue
    if len(failed_to_load) > 0:
        raise HomebrewProcessingException(f"Failed to process {','.join(failed_to_load)}")

    homebrew_list.sort(reverse=True)
    return homebrew_list
