package api

import (
	"bytes"
	"mime/multipart"
)

type FilePart struct {
	Filename string
	Content  []byte
}

func MultipartFiles(files []FilePart) ([]byte, string, error) {
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	for _, file := range files {
		part, err := writer.CreateFormFile("files", file.Filename)
		if err != nil {
			return nil, "", err
		}
		if _, err = part.Write(file.Content); err != nil {
			return nil, "", err
		}
	}
	if err := writer.Close(); err != nil {
		return nil, "", err
	}
	return body.Bytes(), writer.FormDataContentType(), nil
}
