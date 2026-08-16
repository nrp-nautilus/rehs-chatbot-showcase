import json
import shutil
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter

shutil.rmtree("recycling/chunks", ignore_errors=True)
Path("recycling/chunks").mkdir(parents=True, exist_ok=True)

splitter = RecursiveCharacterTextSplitter(
    chunk_size=2000,
    chunk_overlap=400,
)

docs = Path("recycling_markdown")

chunk_count = 0
files = list(docs.rglob("*.md")) + list(docs.rglob("*.mdx"))

for md_file in files:

    text = md_file.read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n").strip()

    if not text:
        continue

    page_name = md_file.relative_to(docs).with_suffix("").as_posix().replace("/", "__")
    title = md_file.stem.replace("-", " ").title()
    relative_path = md_file.relative_to(Path(".")).as_posix()

    url = (
        f"https://github.com/AviAtharvAnand/"
        f"rehs-2026-avi/blob/main/rchatbot/{relative_path}"
    )

    chunks = splitter.split_text(text)

    for i, chunk in enumerate(chunks, start=1):

        data = {
            "id": f"{page_name}__{i:03}",
            "source_url": url,
            "title": title,
            "text": chunk,
        }

        # fill blanks
        outfile = Path("recycling/chunks") / f"{data['id']}.json"

        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        chunk_count += 1

print(f"Created {chunk_count} chunks.")