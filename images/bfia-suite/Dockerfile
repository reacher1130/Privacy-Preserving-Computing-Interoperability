ARG BFIA_CPP_IMAGE=ppci/bfia-cpp:numerics-20260914-v2
ARG BFIA_PYTHON_BASE=ppci/bfia-python:amd64-20260908
FROM ${BFIA_CPP_IMAGE} AS engine
USER 0
# The tested C++ engine needs newer glibc than the Python dependency image.
RUN set -eu; mkdir -p /bfia-engine/lib /bfia-engine/licenses; \
    cp /app/ic_main /bfia-engine/ic_main; \
    ldd /app/ic_main > /bfia-engine/dependencies.txt; \
    ! grep -q 'not found' /bfia-engine/dependencies.txt; \
    for library in $(awk '/=> \// {print $3} $1 ~ /^\// {print $1}' /bfia-engine/dependencies.txt); do \
      cp -L "$library" "/bfia-engine/lib/$(basename "$library")"; \
    done; \
    for package in libc6 libgomp1 libgcc-s1 libstdc++6; do \
      if test -f "/usr/share/doc/$package/copyright"; then \
        cp "/usr/share/doc/$package/copyright" "/bfia-engine/licenses/$package-copyright"; \
      fi; \
    done; \
    sha256sum /app/ic_main > /bfia-engine/binary.sha256

FROM ${BFIA_PYTHON_BASE}
ARG SOURCE_REVISION=unknown
USER 0
LABEL org.opencontainers.image.title="PPCI BFIA eight-algorithm sample suite" \
      org.opencontainers.image.source="https://github.com/reacher1130/Privacy-Preserving-Computing-Interoperability" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      kuscia.secretflow.config-templates="" \
      kuscia.secretflow.deploy-templates=""
COPY --from=engine /bfia-engine/ /opt/bfia/engine/
COPY source/ /opt/bfia/secretflow/
COPY licenses/ /opt/bfia/licenses/
COPY rg /usr/local/bin/rg
COPY source-manifest.json /opt/bfia/source-manifest.json
COPY entrypoint.py /usr/local/bin/bfia-suite
COPY ic-main.sh /opt/bfia/secretflow/interconnection-impl/bazel-bin/ic_impl/ic_main
ENV PYTHONPATH=/opt/bfia/secretflow:/opt/bfia/secretflow/interconnection \
    PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
WORKDIR /opt/bfia/secretflow
RUN chmod 0555 /usr/local/bin/rg /usr/local/bin/bfia-suite \
      /opt/bfia/secretflow/interconnection-impl/bazel-bin/ic_impl/ic_main && \
    python3 -c 'import numpy, secretflow, spu, heu, interconnection, sklearn' && \
    /opt/bfia/engine/lib/ld-linux-x86-64.so.2 --library-path /opt/bfia/engine/lib \
      --list /opt/bfia/engine/ic_main
ENTRYPOINT ["/usr/local/bin/bfia-suite"]
