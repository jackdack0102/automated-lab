#!/usr/bin/env bash

# Thư mục đầu ra
OUTPUT_DIR=".ai"
OUTPUT_FILE="$OUTPUT_DIR/REPO_MAP.md"

mkdir -p "$OUTPUT_DIR"

# Danh sách bỏ qua khi dùng tree/find
EXCLUDE_DIRS="node_modules|\.git|\.next|dist|build|coverage|\.venv|vendor|tmp|\.DS_Store"

echo "# REPO MAP & CONTEXT" > "$OUTPUT_FILE"
echo "Generated at: $(date)" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "## 1. Directory Structure" >> "$OUTPUT_FILE"
echo '```' >> "$OUTPUT_FILE"

# Dùng tree nếu có, nếu không thì fallback sang find
if command -v tree &> /dev/null; then
    tree -a -I "$EXCLUDE_DIRS" --noreport >> "$OUTPUT_FILE"
else
    find . -maxdepth 4 \
        -not -path '*/.*' \
        -not -path './node_modules*' \
        -not -path './dist*' \
        -not -path './build*' \
        -not -path './.venv*' | sort | sed -e 's;[^/]*/;|--;g' -e 's;|--;|;g' >> "$OUTPUT_FILE"
fi

echo '```' >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Gom nội dung các file config / documentation quan trọng (nếu có)
echo "## 2. Key Files Content" >> "$OUTPUT_FILE"

KEY_FILES=("README.md" "package.json" "pyproject.toml" "go.mod" "Cargo.toml" "Dockerfile" "docker-compose.yml")

for file in "${KEY_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "### File: \`$file\`" >> "$OUTPUT_FILE"
        echo '```' >> "$OUTPUT_FILE"
        cat "$file" >> "$OUTPUT_FILE"
        echo '' >> "$OUTPUT_FILE"
        echo '```' >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
done

echo "✅ Generated $OUTPUT_FILE successfully!"