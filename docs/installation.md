# Installation

## Ubuntu / VirtualBox

Requirements:

- Docker
- Kind
- kubectl
- Python 3.11 or newer
- Node.js 20 or newer

Create the three-node cluster:

```bash
./setup.sh
```

For an existing Kind cluster, do not run the setup script with recreation behavior. Configure `KUBECONFIG` and run `docker compose up -d prometheus grafana backend` if Prometheus and Grafana are not already deployed.

Start the application:

```bash
./start.sh
```

Open `http://localhost:5173`.
