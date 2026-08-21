FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .

# torch comes in via sentence-transformers, and the default PyPI wheel declares
# CUDA dependencies on linux/aarch64 as well as x86 — a build here pulls ~445MB
# of nvidia-cudnn plus the rest of the CUDA toolchain into an image that runs
# embeddings on the CPU and has no GPU to use them with. Installing torch from
# PyTorch's CPU index first satisfies the dependency, so the requirements pass
# below leaves it alone. Drop this line if joel ever runs on a GPU host.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install --no-cache-dir -r requirements.txt
COPY joel ./joel
ENV JOEL_DATA=/app/data
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "joel.app:app", "--host", "0.0.0.0", "--port", "8000"]
