# Security policy

CloakMill is pre-release software. No version is currently supported for production processing of private datasets. The repository foundation does not provide a working de-identification or pseudonymization pipeline.

## Report privately

Do not disclose a vulnerability, exploit, customer dataset, credential, or identity mapping in a public issue or pull request.

When available, use the repository's **Security → Report a vulnerability** flow. Private vulnerability reporting availability depends on repository visibility and GitHub configuration. While the repository is private, use a restricted channel already shared with its owner, or a restricted issue containing a synthetic reproduction and no secrets. If no private channel is available, request a private reporting route without including vulnerability details.

Include affected code/version, impact, a minimal synthetic reproduction, and any proposed mitigation. Do not upload real affected data. No response-time SLA or bug bounty is offered at this stage.

## Contributor safeguards

Keep customer content, secrets, model assets, local registries, and transformation outputs outside version control. Avoid sensitive values in logs and exceptions. Treat model output, source documents, archives, and serialized content as untrusted input. Preserve the distinction between pseudonymization and anonymity.
