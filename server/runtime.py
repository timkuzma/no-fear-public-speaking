"""Single-process container entrypoint with explicit proxy trust."""
import ipaddress
import os
import uvicorn


def main():
    trusted = os.getenv('TRUSTED_PROXY_IPS', '127.0.0.1')
    for address in trusted.split(','):
        ipaddress.ip_address(address.strip())  # Reject wildcard trust and malformed config.
    uvicorn.run('server.app:app', host='0.0.0.0', port=8080, workers=1,
                access_log=False, forwarded_allow_ips=trusted, timeout_graceful_shutdown=30,
                limit_concurrency=128, backlog=128)


if __name__ == '__main__':
    main()
