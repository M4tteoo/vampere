# Wattson chat assistant (FastAPI) on Render (free web service, Docker runtime).
# Assembled by deploy/assistant/deploy.sh and pushed to the deploy-assistant branch; not built from main.
FROM python:3.13-slim

# Non-root user. Render sets PORT (default 10000); 7860 is only the fallback.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" PYTHONUNBUFFERED=1 \
    ASSISTANT_HOST=0.0.0.0 PORT=7860
WORKDIR /home/user/app

COPY --chown=user requirements.txt requirements-assistant.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt -r requirements-assistant.txt

COPY --chown=user . .
EXPOSE 7860
CMD ["python", "-m", "assistant", "serve"]
