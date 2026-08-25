#!/usr/bin/env bash
set -euo pipefail

version="${1:?Usage: $0 VERSION}"

if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([~+-][0-9A-Za-z.+~]+)?$ ]]; then
    echo "Invalid Debian package version: $version" >&2
    exit 1
fi

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
package_root="$(mktemp -d)"
output_dir="$project_dir/dist"
output_file="$output_dir/stowmark-observability_${version}_all.deb"

cleanup() {
    rm -rf "$package_root"
}
trap cleanup EXIT

install -d \
    "$package_root/DEBIAN" \
    "$package_root/etc/default" \
    "$package_root/etc/systemd/system" \
    "$package_root/opt/stowmark-observability" \
    "$output_dir"

install -m 0644 "$project_dir/compose.yaml" \
    "$package_root/opt/stowmark-observability/compose.yaml"
cp -R "$project_dir/config" "$package_root/opt/stowmark-observability/config"
cp -R "$project_dir/dashboards" "$package_root/opt/stowmark-observability/dashboards"

install -m 0644 "$project_dir/packaging/stowmark-observability.service" \
    "$package_root/etc/systemd/system/stowmark-observability.service"
install -m 0644 "$project_dir/packaging/stowmark-observability.env" \
    "$package_root/etc/default/stowmark-observability"

sed "s/@VERSION@/$version/g" "$project_dir/packaging/control" \
    > "$package_root/DEBIAN/control"
install -m 0644 "$project_dir/packaging/conffiles" "$package_root/DEBIAN/conffiles"
install -m 0755 "$project_dir/packaging/postinst" "$package_root/DEBIAN/postinst"
install -m 0755 "$project_dir/packaging/prerm" "$package_root/DEBIAN/prerm"
install -m 0755 "$project_dir/packaging/postrm" "$package_root/DEBIAN/postrm"

chmod -R u=rwX,go=rX "$package_root"
dpkg-deb --root-owner-group --build "$package_root" "$output_file"
echo "Built $output_file"
