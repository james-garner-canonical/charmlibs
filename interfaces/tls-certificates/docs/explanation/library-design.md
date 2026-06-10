# Library design

The `tls-certificates` interface specification (see the [interface reference](../../interface/v1/README.md)) describes only the wire protocol: a requirer publishes certificate signing requests (CSRs) on its relation data, and a provider publishes signed certificates back. Everything else — generating keys, building CSRs, triggering renewals, storing material safely — is left to the charm at each end of the relation.

This library handles those responsibilities for the requirer side, so that charm authors can focus on *what* should be in their certificates rather than *how* to obtain and manage them.

## What the library does for you

When a charm uses `TLSCertificatesRequiresV4`, the library:

- Generates an RSA private key on first use and stores it in a Juju secret owned by the requiring charm.
- Builds a CSR from the `CertificateRequestAttributes` you supply and writes it to relation data.
- Receives the signed certificate from the provider and emits a `certificate_available` event.
- Tracks certificate expiry and triggers renewal automatically (see below).

Because the library generates the private key, upgrading a charm that previously managed its own key will cause one certificate rotation: the library generates a new key, the previous CSR no longer matches, and a new certificate is issued. If you need to retain a specific key — for example, to avoid that rotation — you can pass it to `TLSCertificatesRequiresV4` at instantiation time.

## How automatic renewals work

The library renews certificates without any code in the requirer charm:

1. When the requirer receives a certificate from the provider, it stores the certificate in a Juju secret with an expiry set ahead of the certificate's own expiry.
2. A `certificate_available` event is emitted, prompting the requiring charm to write the certificate where its workload expects it.
3. When the Juju secret expires, the library removes the old CSR from the relation data, deletes the secret, generates a new CSR, and writes the new CSR to the relation data.
4. The provider reads the new CSR, issues a new certificate, and writes it to relation data.
5. The requirer reads the new certificate, stores it in a fresh Juju secret, and re-emits `certificate_available`.

The requiring charm only ever has to handle `certificate_available`; the rest is managed by the library.
