# ==============================================================================
# Dockerfile for Abend Lab fMRI Analysis Pipelines (TIM & WAR)
#
# Packages:
#   - AFNI (afni_proc.py, sswarper2, 3dDeconvolve, 3dREMLfit, 3dttest++, 3dLMEr, @chauffeur_afni)
#   - R + statistical packages required by 3dLMEr (lme4, lmerTest, afex, snow, phia)
#   - Xvfb & netpbm (headless rendering for @chauffeur_afni)
#   - wkhtmltopdf (HTML-to-PDF conversion for AFNI QC reports)
#   - Google Cloud SDK (`gcloud storage` for high-speed parallel GCS transfers)
#   - Python 3 + pipeline dependencies
#   - Pre-bundled MNI152_2009_template.nii.gz and MNI152_2009_template_SSW.nii.gz
# ==============================================================================

FROM afni/afni_make_build:latest

# The upstream afni_make_build image switches to a non-root user; switch back to root for package installation
USER root

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUNBUFFERED=1

# 1. Install system utilities, Xvfb, wkhtmltopdf, R packages for 3dLMEr, and Google Cloud CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        unzip \
        rsync \
        tcsh \
        xvfb \
        xauth \
        netpbm \
        wkhtmltopdf \
        dcm2niix \
        python3 \
        python3-pip \
        r-base \
        r-base-dev \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

# 2. Ensure R packages needed by AFNI's 3dLMEr are installed
RUN Rscript -e "options(repos = c(CRAN = 'https://cloud.r-project.org')); \
    pkgs <- c('lme4', 'lmerTest', 'afex', 'snow', 'phia', 'data.table'); \
    missing <- pkgs[!pkgs %in% installed.packages()[, 'Package']]; \
    if (length(missing) > 0) install.packages(missing, Ncpus = parallel::detectCores())" \
    || true

# 3. Prepare MNI templates directory (/opt/afni_templates)
RUN mkdir -p /opt/afni_templates
COPY tim_analysis/MNI152_2009_template.nii.gz /opt/afni_templates/MNI152_2009_template.nii.gz

# Locate or download MNI152_2009_template_SSW.nii.gz so sswarper2 never needs it in input_dir
RUN SSW_EXISTING=$(find / -name "MNI152_2009_template_SSW.nii.gz" 2>/dev/null | head -n 1 || true); \
    if [ -n "$SSW_EXISTING" ] && [ -f "$SSW_EXISTING" ]; then \
        ln -sf "$SSW_EXISTING" /opt/afni_templates/MNI152_2009_template_SSW.nii.gz; \
    else \
        curl -fsSL https://afni.nimh.nih.gov/pub/dist/atlases/afni_atlases_dist/MNI152_2009_template_SSW.nii.gz \
            -o /opt/afni_templates/MNI152_2009_template_SSW.nii.gz || true; \
    fi

# 4. Install Python dependencies into an explicit target directory (/opt/pydeps) on PYTHONPATH
ENV PYTHONPATH=/opt/pydeps:/opt/user_pip_packages/lib/python3.6/site-packages:/app
WORKDIR /app
COPY tim_analysis/requirements.txt /app/requirements.txt
RUN mkdir -p /opt/pydeps \
    && python3 -m pip install --no-cache-dir --upgrade --target=/opt/pydeps -r /app/requirements.txt \
    && chmod -R a+rX /opt/pydeps \
    && python3 -c "import rich, toml, pandas, numpy, pdfkit, fpdf, pypdf; from pypdf import PdfWriter; from google.cloud import storage; print('Python dependencies verified!')"

# 5. Copy pipeline codebase
COPY cloud/ /app/cloud/
COPY tim_analysis/ /app/tim_analysis/
COPY war_analysis/ /app/war_analysis/

RUN chmod +x /app/cloud/entrypoint.sh \
    /app/tim_analysis/scripts/*.sh \
    /app/war_analysis/scripts/*.sh \
    && mkdir -p /scratch \
    && python3 -m py_compile /app/cloud/gcs_helper.py /app/tim_analysis/run_analysis.py /app/war_analysis/run_analysis.py /app/tim_analysis/export_results.py /app/war_analysis/export_results.py /app/tim_analysis/concatenate_reports.py /app/war_analysis/concatenate_reports.py

ENTRYPOINT ["/app/cloud/entrypoint.sh"]
CMD ["--help"]
