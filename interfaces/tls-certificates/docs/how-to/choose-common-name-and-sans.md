# Choose values for the common name and SAN attributes

When building a `CertificateRequestAttributes` you must decide what to put in
the certificate's common name and Subject Alternative Name (SAN) fields. There
is no single correct answer; the right values depend on what the certificate is
used for. The guidance below covers the most common cases.

The appropriate SANs depend on the type of communication: internal unit-to-unit
communication, or external client-to-server API communication.

## Internal communication

Different applications can use different mechanisms for one unit to access another.
If units communicate with each other using IP addresses, then the IP address provided by Juju for connecting to that unit (accessible through the `ingress_address` attribute of the Network class in Ops) should be included in the certificate’s IP SANs.
For Kubernetes charms, it is often sufficient to include the Kubernetes Service DNS name (for example, `myapp-endpoints.myapp.svc.cluster.local`).
If internal communication relies on externally resolvable names, the charm should allow those names to be configured and must provide a mechanism to resolve them to the corresponding IP addresses.

## External communication

When a unit is accessed directly by a client (either a user or another application), the certificate should cover all possible ways the API can be reached.
If clients are expected to connect using an IP address, that IP should be included in the IP SANs.
If they connect using a domain name, that name should be included in the DNS SANs.
The domain name should be configurable in the requirer charm.
A better approach is to offload TLS termination to a load balancer or proxy, and have the API accessed from behind it. In that case, TLS termination occurs at the load-balancer level, and backend units do not need to manage individual certificates for external clients.