package api

import (
	"bytes"
	"io"
	"mime"
	"mime/multipart"
	"testing"
)

func TestMultipartFilesPreservesOrderedNamesAndBytes(t *testing.T) {
	files := []FilePart{
		{"目录/config.toml", []byte{0, 255, '\n'}},
		{"../escape.txt", []byte("rejected by the application")},
		{"目录/config.toml", []byte("second occurrence")},
		{`literal\name.txt`, []byte{}},
	}
	body, contentType, err := MultipartFiles(files)
	if err != nil {
		t.Fatal(err)
	}
	mediaType, parameters, err := mime.ParseMediaType(contentType)
	if err != nil || mediaType != "multipart/form-data" {
		t.Fatalf("content type %q: %v", contentType, err)
	}
	reader := multipart.NewReader(bytes.NewReader(body), parameters["boundary"])
	for index, expected := range files {
		part, err := reader.NextPart()
		if err != nil {
			t.Fatalf("part %d: %v", index, err)
		}
		_, disposition, err := mime.ParseMediaType(part.Header.Get("Content-Disposition"))
		if err != nil || disposition["name"] != "files" || disposition["filename"] != expected.Filename {
			t.Fatalf("part %d disposition %v: %v", index, disposition, err)
		}
		actual, err := io.ReadAll(part)
		if err != nil || !bytes.Equal(actual, expected.Content) {
			t.Fatalf("part %d bytes %v: %v", index, actual, err)
		}
	}
	if _, err := reader.NextPart(); err != io.EOF {
		t.Fatalf("unexpected extra part: %v", err)
	}
}
