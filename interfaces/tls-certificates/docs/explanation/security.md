# Security

This page describes the security-relevant aspects of the requirer side of the
`tls-certificates` library. For the wire-level guarantees of the interface
itself, see the [interface reference](../../interface/v1/README.md). To report
a security issue in this library, follow the
[charmlibs security policy](https://github.com/canonical/charmlibs/blob/main/SECURITY.md).

## Private key management

The library never transmits the requirer's private key over the relation. Only
certificate signing requests (CSRs) and the resulting certificates cross the
relation; the private key stays inside the requiring charm's data.

### Storage at rest

The library stores the private key in a Juju secret owned by the requiring
charm. Only the charm itself and a Juju administrator can read the secret.
For details of the secret backend Juju uses, see the
[Juju documentation on secret backends](https://documentation.ubuntu.com/juju/3.6/howto/manage-secret-backends/#manage-secret-backends).

### Key generation

Private keys are generated using the
[RSA algorithm](https://en.wikipedia.org/wiki/RSA_(cryptosystem)).

### Key labelling and multiple integrations

When a requirer charm participates in more than one `tls-certificates`
integration, the library stores one private key per relation. The Juju secret
labels include both the unit number and the relation name, so each integration
gets its own key and certificate without collisions.

Charm authors can rotate the private key by calling the `regenerate_private_key` method which will generate a new private key, remove old certificate requests, and send new ones to the TLS provider.