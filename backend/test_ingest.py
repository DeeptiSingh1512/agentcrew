import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Ingest a PDF into the local document store.")
    parser.add_argument("pdf_path", help="Path to the PDF file to ingest")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.is_file():
        parser.error(f"PDF file does not exist: {pdf_path}")
    if pdf_path.stat().st_size == 0:
        parser.error(f"PDF file is empty (0 bytes): {pdf_path}")

    from app.ingest.pipeline import ingest_pdf

    chunk_count = ingest_pdf(str(pdf_path), pdf_path.name)
    print(f"Stored {chunk_count} chunks from {pdf_path.name}.")


if __name__ == "__main__":
    main()