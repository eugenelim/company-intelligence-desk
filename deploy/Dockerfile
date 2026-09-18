# One image, both deployables, per ADR-0003 D3. `worker-runtime.md` § How
# workers are provisioned: nothing agent-specific is baked in, so adding an
# agent is a `policy-author` write rather than an image rebuild.
# Digest-pinned, so the image a recorded result was measured against cannot
# change with no diff.
FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285

# psycopg[binary] ships its own libpq wheel, so no build toolchain is needed.
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
# NOT reproducible: direct dependencies are exact-pinned in the manifest,
# but every transitive package resolves fresh at build time with no
# lockfile and no integrity hashes, so the installed set can change without
# a diff. Recorded rather than fixed: a hash-locked resolution needs a tool
# (`uv`, `pip-tools`) the plan's dependency list does not carry, which is an
# Ask-first boundary. The verification ledger records it as not established.
RUN pip install --no-cache-dir .

# Unbuffered, so `docker logs` shows a line the moment it is written. A killed
# container otherwise loses whatever was still in the buffer, which is exactly
# the evidence the fault-injection suite reads.
ENV PYTHONUNBUFFERED=1

# The default entry point is the worker; the API overrides `command`.
CMD ["ced-worker"]
