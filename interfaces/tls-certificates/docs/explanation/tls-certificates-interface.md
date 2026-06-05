# The TLS Certificates Interface

The whole idea behind the TLS Certificates interface is that charms can request TLS certificates to TLS providers without ever sharing their private key.

The TLS Certificates Requirer (through the use of the TLS Certificates Library) generates its private key and a Certificate Signing Request (CSR). This CSR is inserted into its unit (or application) relation data. 

The TLS Certificates Provider reads this CSR, signs a certificate for it and inserts this certificate into its application relation data.

The TLS Certificates Requirer then reads the certificate, and typically stores it in a file on the workload.

![image](https://discourse-charmhub-io.s3.dualstack.eu-west-2.amazonaws.com/original/2X/3/381e8a5aedcca8bba7357a417402ab48de000b78.png)