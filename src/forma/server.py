"""FastAPI server for the forma document conversion toolkit."""

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from .conversion.workflow import run_conversion
from .shared.custom_types import Strategy

app = FastAPI()


@app.post("/convert/")
async def convert_file(
    file: UploadFile = File(...),
    strategy: Strategy = Strategy.AUTO,
    background_tasks: BackgroundTasks = None,
) -> FileResponse:
    """Converts an uploaded document to Markdown and returns the result.

    - **file**: The document to convert (PDF, DOCX, PPTX, image).
    - **strategy**: Conversion strategy (`auto`, `fast`, `deep`).
    """
    # Create a temporary directory to store the uploaded file and the output.
    temp_dir_str = tempfile.mkdtemp()
    temp_dir = Path(temp_dir_str)
    input_path = temp_dir / file.filename
    output_dir = temp_dir / "output"
    output_dir.mkdir()

    print("被调用了")
    print("input_path: ", input_path)
    print("output_dir: ", output_dir)

    # Save the uploaded file to the temporary directory.
    try:
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    # Run the conversion process.
    try:
        run_conversion(
            inputs=[input_path],
            output_dir=output_dir,
            strategy=strategy,
            recursive=False,  # We are processing a single file.
        )
    except Exception as e:
        # Cleanup temp directory on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")

    # Find the output file.
    output_files = list(output_dir.glob("*.md"))
    if not output_files:
        # Cleanup temp directory if nothing produced
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail="Conversion did not produce an output file.",
        )

    output_path = output_files[0]

    # Ensure cleanup after response is sent
    if background_tasks is not None:
        background_tasks.add_task(shutil.rmtree, temp_dir, True)

    # Return the converted file.
    return FileResponse(
        path=output_path,
        media_type="text/markdown",
        filename=f"{input_path.stem}.md",
    )
