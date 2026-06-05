# Trust CA certificates of TLS Providers

In the Juju ecosystem, multiple TLS providers can be used to issue certificates for applications and units.
* [self-signed-certificates](https://charmhub.io/self-signed-certificates)
* [vault](https://charmhub.io/vault-k8s)
* [lego](https://charmhub.io/lego)
* [manual-tls-certificates](https://charmhub.io/manual-tls-certificates)

In some cases, the CA certificates used by these providers are self-signed. This means that the certificates they issue will not be trusted by default by other applications or clients unless the CA is explicitly trusted.

### Best Practices for Production Deployments

* **Internal Communication (Unit-to-Unit)**
As described in the [internal communication guide](https://discourse.charmhub.io/t/deployment-blueprint-securing-internal-communication/18382), `self-signed-certificates` can be used to secure intra-application traffic.
In this case:
  * Each unit of an application receives the CA certificate as part of the relation data from the [tls-certificates](https://charmhub.io/tls-certificates-interface) integration.
  * The CA is the direct issuer of the application’s leaf certificate.
  * Trusting this CA is sufficient to establish trust in the leaf certificates.
* **API Communication**
For more complex deployments that [secure API communication](https://discourse.charmhub.io/t/deployment-blueprint-securing-api-communication/18385), client applications should trust the CA directly from the CA provider, not from the application.
  * The CA certificate can be obtained by integrating with the provider over the [certificates-transfer](https://charmhub.io/certificate-transfer-interface) interface.
  * When the provider uses intermediate CA, it is recommended to trust the provider with the root CA (or the highest CA in the hierarchy). However this is not mandatory.