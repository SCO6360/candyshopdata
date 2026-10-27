FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY candyshop ./candyshop
RUN pip install --no-cache-dir .
ENV CANDY_DATA_DIR=/app/data
EXPOSE 8800
CMD ["candy", "serve-api", "--host", "0.0.0.0", "--port", "8800"]
