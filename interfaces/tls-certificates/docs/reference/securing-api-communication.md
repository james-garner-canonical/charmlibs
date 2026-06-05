# Secure Client <-> App Communication

You should deploy a TLS provider in a different model to provide certificates for applications to secure API communication.

This provider will issue the certificates used to secure traffic between clients and applications.

Supported TLS providers include:

- [self-signed-certificates](https://charmhub.io/self-signed-certificates)
- [vault](https://charmhub.io/vault-k8s)
- [lego](https://charmhub.io/lego)
- [manual-tls-certificates](https://charmhub.io/manual-tls-certificates)

> Note: Deploying the TLS provider in a different model is not mandatory. In smaller or simpler setups, the provider and requirer applications can be in the same model.

## 1. Using an Ingress

In most cases, applications are accessed behind an ingress.

The ingress will:

1. Integrate with the TLS provider in APP mode to secure external (client-to-ingress) communication.
2. Terminate TLS traffic before passing requests to backend applications.

For internal traffic between ingress and backends, you can:

- Use a provider like [self-signed-certificates](https://charmhub.io/self-signed-certificates).
- Integrate each backend application with the provider over the [tls-certificates](https://charmhub.io/tls-certificates-interface) interface in UNIT mode.
- Integrate the ingress with the provider over the [certificates-transfer](https://charmhub.io/certificate-transfer-interface) interface so that the ingress trusts the CA used by the backend units.
- This ensures the ingress can validate backend-provided certificate chains that lead to the trusted CA.


## 2. Trust Establishment Between Clients and Applications

For TLS to work correctly:

- **Clients** must trust the CA that issued the application’s leaf certificate.
- **Applications** must present a valid chain that leads to that trusted CA.

### Examples:

- **Public CA (`lego` with Let’s Encrypt`)**:
    
    Certificates are usually trusted by default.
    
- **Self-signed CA (`self-signed-certificates`, `vault`, or `manual-tls-certificates`)**:
    
    Clients (or client applications) must explicitly trust the CA.
    
    For Juju-integrated client applications, this is achieved by integrating with the provider over the `certificates-transfer` interface.

![external](https://discourse-charmhub-io.s3.eu-west-2.amazonaws.com/optimized/2X/0/05bb9c7e09d9dda9d1b6a60bdb2a239c22953fd2_2_690x376.jpeg)