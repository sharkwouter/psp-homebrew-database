#!/usr/bin/env python3

import datetime
import os
import json
import logging
import shutil
import gzip

import jinja2
import jsonschema

from homebrew_database.homebrew import Homebrew, get_homebrew_list


DATA_DIR = "data"
DIST_DIR = "dist"
RESOURCE_DIR = "resources"
TEMPLATE_DIR = "templates"
TEMP_DIR = "temp"
SCHEMA_DIR = os.path.join(RESOURCE_DIR, "schemas")


def create_dist_dir() -> None:
    if os.path.isdir(DIST_DIR):
        for file_name in os.listdir(DIST_DIR):
            file_path = os.path.join(DIST_DIR, file_name)
            if not os.path.isdir(file_path):
              os.remove(file_path)
            else:
              shutil.rmtree(file_path)
        os.rmdir(DIST_DIR)
    os.mkdir(DIST_DIR)


def create_json_catalog(homebrew_list: list[Homebrew]) -> None:
    schema_name = "catalog.schema.json"
    generated_at = datetime.datetime.now().replace(microsecond=0)
    homebrew_dict = {
        "schema": f"schemas/{schema_name}",
        "generated_at": generated_at.isoformat() + "Z",
        "apps": []
    }
    for homebrew in homebrew_list:
        homebrew_dict["apps"].append(homebrew.to_dict())

    # Validate the generated dict against the schema
    json_schema_path = os.path.join(SCHEMA_DIR, schema_name)
    with open(json_schema_path, "r") as fd:
        json_schema = json.loads(fd.read())
    json_output = json.dumps(homebrew_dict)
    jsonschema.validate(instance=json.loads(json_output), schema=json_schema)

    with open(os.path.join(DIST_DIR, "catalog.json"), "w") as fd:
        fd.write(json_output)


def create_pkgi_catalogs(homebrew_list: list[Homebrew]) -> None:
    categories = ["game", "emulator", "application"]
    content_per_category = {}
    for category in categories:
        content_per_category[category] = ""

    for homebrew in homebrew_list:
        if homebrew.category == "game":
            pkgi_type = 1
        elif homebrew.category == "emulator":
            pkgi_type = 7
        elif homebrew.category == "application":
            pkgi_type = 8
        else:
            continue

        release = homebrew.releases[0]
        content_per_category[homebrew.category] += f",{pkgi_type},{homebrew.name},\"{homebrew.summary}\",,{release.url},{release.size},{release.sha256}\n"

    for category in categories:
        with open(os.path.join(DIST_DIR, f"pkgi_{category}s.txt"), "w") as fd:
            fd.write(content_per_category[category])

    with open(os.path.join(DIST_DIR, "pkgi.txt"), "w") as fd:
        content = "".join(content_per_category[category] for category in categories)
        fd.write(content)


def create_pkgi_config() -> None:
    # Only create this file if the build is happening from the GitHub CI
    # Otherwise we have no clue what the url should be
    if not os.environ.get("CI"):
        return
    owner,repo = os.environ["GITHUB_REPOSITORY"].split("/")

    config_content = f"url https://{owner}.github.io/{repo}/pkgi.txt"
    with open(os.path.join(DIST_DIR, "config.txt"), "w") as fd:
        fd.write(config_content)


def create_binary_catalog(homebrew_list: list[Homebrew]) -> None:
    homebrew_count = len(homebrew_list)
    homebrew_count_size = 4

    offset_size = 4

    category_size = 1
    id_length_size = 1
    name_length_size = 1
    summary_length_size = 1
    author_length_size = 1
    tag_length_size = 1
    url_length_size = 1
    published_at_size = 4
    size_size = 4
    homebrew_struct_size = (
        category_size +
        id_length_size +
        offset_size +
        name_length_size +
        offset_size +
        summary_length_size +
        offset_size +
        author_length_size +
        offset_size +
        tag_length_size +
        offset_size +
        url_length_size +
        offset_size +
        published_at_size +
        size_size
    )
    current_offset = homebrew_count_size + (homebrew_count * homebrew_struct_size)

    strings_to_append = []
    with open(os.path.join(DIST_DIR, "catalog.bin"), "w+b") as fd:
        fd.write(homebrew_count.to_bytes(homebrew_count_size, byteorder='little', signed=False))
        for homebrew in homebrew_list:
            last_release = homebrew.get_last_release()

            # Category
            if homebrew.category == "game":
                fd.write(int(1).to_bytes(category_size, byteorder='little', signed=False))
            elif homebrew.category == "emulator":
                fd.write(int(2).to_bytes(category_size, byteorder='little', signed=False))
            elif homebrew.category == "application":
                fd.write(int(3).to_bytes(category_size, byteorder='little', signed=False))
            else:
                fd.write(int(1).to_bytes(category_size, byteorder='little', signed=False))

            # Id
            id_length = len(homebrew.id.encode("utf-8"))
            fd.write(id_length.to_bytes(id_length_size, byteorder='little', signed=False))
            fd.write(current_offset.to_bytes(offset_size, byteorder='little', signed=False))
            strings_to_append.append(homebrew.icon)
            current_offset += id_length

            # Name
            name_length = len(homebrew.name.encode("utf-8"))
            fd.write(name_length.to_bytes(name_length_size, byteorder='little', signed=False))
            fd.write(current_offset.to_bytes(offset_size, byteorder='little', signed=False))
            strings_to_append.append(homebrew.name)
            current_offset += name_length

            # Summary
            summary_length = len(homebrew.summary.encode("utf-8"))
            fd.write(summary_length.to_bytes(summary_length_size, byteorder='little', signed=False))
            fd.write(current_offset.to_bytes(offset_size, byteorder='little', signed=False))
            strings_to_append.append(homebrew.summary)
            current_offset += summary_length

            # Author
            author_length = len(homebrew.author.encode("utf-8"))
            fd.write(author_length.to_bytes(author_length_size, byteorder='little', signed=False))
            fd.write(current_offset.to_bytes(offset_size, byteorder='little', signed=False))
            strings_to_append.append(homebrew.author)
            current_offset += author_length

            # Tag
            tag_length = len(last_release.tag.encode("utf-8"))
            fd.write(tag_length.to_bytes(tag_length_size, byteorder='little', signed=False))
            fd.write(current_offset.to_bytes(offset_size, byteorder='little', signed=False))
            strings_to_append.append(last_release.tag)
            current_offset += tag_length

            # Url
            url_length = len(last_release.url.encode("utf-8"))
            fd.write(url_length.to_bytes(url_length_size, byteorder='little', signed=False))
            fd.write(current_offset.to_bytes(offset_size, byteorder='little', signed=False))
            strings_to_append.append(last_release.url)
            current_offset += url_length

            # Published_at
            timestamp = int(datetime.datetime.combine(last_release.published_at, datetime.time()).timestamp())
            fd.write(timestamp.to_bytes(published_at_size, byteorder='little', signed=False))

            # Size
            fd.write(last_release.size.to_bytes(size_size, byteorder='little', signed=False))

        for string in strings_to_append:
            fd.write(string.encode("utf-8"))

        fd.seek(0, 0)
        with gzip.open(os.path.join(DIST_DIR, "catalog.bin.gz"), "wb") as gzip_fd:
            gzip_fd.write(fd.read())


def create_pages(homebrew_list: list[Homebrew]) -> None:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATE_DIR))

    index_file_name = "index.html"
    index_template = env.get_template(index_file_name)

    with open(os.path.join(DIST_DIR, index_file_name), "w") as fd:
        fd.write(
            index_template.render(
                homebrew_list=homebrew_list
            )
        )

    homebrew_template = env.get_template("homebrew.html")
    for homebrew in homebrew_list:
        with open(os.path.join(DIST_DIR, f"{homebrew.id}.html"), "w") as fd:
            fd.write(
                homebrew_template.render(
                    homebrew=homebrew
                )
            )


def copy_resources() -> None:
    for file_name in os.listdir(RESOURCE_DIR):
        file_path = os.path.join(RESOURCE_DIR, file_name)
        if os.path.isdir(file_path):
            shutil.copytree(file_path, os.path.join(DIST_DIR, file_name))
        elif os.path.isfile(file_path):
            shutil.copy2(file_path, DIST_DIR)


def configure_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)


def main() -> None:
    configure_logger()

    create_dist_dir()

    homebrew_list = get_homebrew_list(data_dir=DATA_DIR)
    create_pages(homebrew_list=homebrew_list)
    create_json_catalog(homebrew_list=homebrew_list)
    create_pkgi_catalogs(homebrew_list=homebrew_list)
    create_pkgi_config()
    create_binary_catalog(homebrew_list=homebrew_list)
    copy_resources()

if __name__ == "__main__":
    main()
