#!/usr/bin/env bash

NODE_VERSION="$(<"$APP_DIR/frontend/.node-version")"
NODE_VERSION="${NODE_VERSION//$'\r'/}"

if [ "$(node --version 2>/dev/null || true)" != "v$NODE_VERSION" ]; then
  case "$(uname -s)" in
    Linux)  NODE_OS="linux"; NODE_EXT="tar.xz" ;;
    Darwin) NODE_OS="darwin"; NODE_EXT="tar.gz" ;;
    *) echo "Unsupported OS: $(uname -s)"; return 1 ;;
  esac
  case "$(uname -m)" in
    arm64|aarch64) NODE_ARCH="arm64" ;;
    x86_64) NODE_ARCH="x64" ;;
    *) echo "Unsupported architecture: $(uname -m)"; return 1 ;;
  esac
  NODE_PLAT="$NODE_OS-$NODE_ARCH"
  NODE_DIR="$INSTALL_ROOT/node/node-v$NODE_VERSION-$NODE_PLAT"
  if [ ! -x "$NODE_DIR/bin/node" ]; then
    printf 'Downloading portable Node.js %s...\n' "$NODE_VERSION"
    mkdir -p "$INSTALL_ROOT/node"
    curl -fL "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-$NODE_PLAT.$NODE_EXT" \
      -o "$INSTALL_ROOT/node/node.tar"
    tar -xf "$INSTALL_ROOT/node/node.tar" -C "$INSTALL_ROOT/node"
    rm -f "$INSTALL_ROOT/node/node.tar"
  fi
  export PATH="$NODE_DIR/bin:$PATH"
fi

if [ "$(node --version)" != "v$NODE_VERSION" ]; then
  echo "Node provisioning failed: expected v$NODE_VERSION."
  return 1
fi
