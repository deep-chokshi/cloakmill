// The sample foundation listens only on loopback. Deployment is a later milestone.
process.env.HOSTNAME = "127.0.0.1";
process.env.PORT = "4318";
process.env.NEXT_TELEMETRY_DISABLED = "1";
await import("../.next/standalone/server.js");
