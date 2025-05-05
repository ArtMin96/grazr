## Development Setup Notes

### Nginx Port Binding (Ports 80/443)

The bundled Nginx service is configured to listen on standard ports 80 (HTTP) and 443 (HTTPS). On Linux, binding to ports below 1024 typically requires root privileges or specific capabilities.

Since Grazr runs Nginx as the regular user, you need to grant the `nginx` binary the `CAP_NET_BIND_SERVICE` capability **manually** in your development environment after bundling Nginx. This allows it to use the standard ports without running as root.

#### Command (run after bundling Nginx):

```
# Make sure the path points to the nginx binary inside your bundle directory
sudo setcap 'cap_net_bind_service=+ep' ~/.local/share/grazr/bundles/nginx/sbin/nginx
```

**Important:**

- You need `sudo` access to run `setcap`.
- You might need to re-run this command if you re-bundle or update the Nginx version in your `~/.local/share/grazr/bundles/` directory.
- This manual step is **only for development**. The final `.deb` package installer will include a `postinst` script that runs this `setcap` command automatically upon installation on the user’s system, using the correct installed path (e.g., `/opt/grazr/bundles/...`).
