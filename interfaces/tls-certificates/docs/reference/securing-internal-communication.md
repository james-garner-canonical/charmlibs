# Secure Internal Communication of a Charm

When deploying multiple applications in a Juju model that require TLS for internal communication (e.g., between the units of the same application), we recommend using the [self-signed-certificates](https://charmhub.io/self-signed-certificates) charm.
![internal|690x688](upload://wyI0hteMdmghKvsvuc7XtP5f0jf.png)


Integrate each application with [self-signed-certificates](https://charmhub.io/self-signed-certificates) over the [tls-certificates](https://charmhub.io/tls-certificates-interface) interface in **UNIT** mode. This ensures that  each unit receives its own unique certificate.

The [self-signed-certificates](https://charmhub.io/self-signed-certificates) charm will issue a Certificate object for each unit, containing:

- **Signed leaf certificate** for that specific unit.
- **CA certificate** that signed the leaf certificate.
- **Certificate chain** in the form: `[Signed Leaf Certificate, CA Certificate]`.

## Trust Establishment

Because the CA is self-signed, it is not trusted by default by most systems.

To establish trust:

- Explicitly configure the application to trust the CA certificate provided by `self-signed-certificates`.
- Since the CA directly issues the unit certificates, trusting this CA is sufficient to validate the leaf certificates.

Each application can then configure TLS according to its own requirements, using the provided certificate, CA, and chain.