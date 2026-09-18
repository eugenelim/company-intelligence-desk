# One image, both deployables, per ADR-0003 D3. `worker-runtime.md` § How
# workers are provisioned: nothing agent-specific is baked in, so adding an
# agent is a `policy-author` write rather than an image rebuild.
FROM python:3.13-slim

# psycopg[binary] ships its own libpq wheel, so no build toolchain is needed.
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Unbuffered, so `docker logs` shows a line the moment it is written. A killed
# container otherwise loses whatever was still in the buffer, which is exactly
# the evidence the fault-injection suite reads.
ENV PYTHONUNBUFFERED=1

# The default entry point is the worker; the API overrides `command`.
CMD ["ced-worker"]
