# Use an official Python runtime
FROM python:3.8-slim-buster

# Install build dependencies for TA-Lib
RUN apt-get update && \
    apt-get install -y build-essential curl git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install TA-Lib C library
RUN curl -L https://downloads.sourceforge.net/project/ta-lib/ta-lib/0.4.0/ta-lib-0.4.0-src.tar.gz | tar xvz && \
    cd ta-lib && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib && \
    ldconfig

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/

# Clear state files to avoid conflicts
RUN echo {} > /app/rsi_alerts_sent.json && \
    echo {} > /app/last_trade_time.json && \
    rm -f /app/xrp_balance.json && \
    rm -f /app/eth_balance.json

# Command to run the bot
CMD ["python", "bot.py"]
