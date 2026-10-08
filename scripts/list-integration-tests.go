// Discover integration-only tests using Go's build selection and syntax parser.
// Run as a single file from the candidate source checkout; no private source is
// copied into the public policy repository.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
)

type goPackage struct {
	ImportPath, Dir           string
	TestGoFiles, XTestGoFiles []string
}

type integrationPackage struct {
	ImportPath string            `json:"import_path"`
	Path       string            `json:"path"`
	Tests      []string          `json:"tests"`
	Files      map[string]string `json:"files"`
}

func packages(tagged bool) []goPackage {
	args := []string{"list", "-json"}
	if tagged {
		args = append(args, "-tags", "integration")
	}
	cmd := exec.Command("go", append(args, "./...")...)
	cmd.Stderr = os.Stderr
	data, err := cmd.Output()
	if err != nil {
		panic(fmt.Errorf("go package discovery: %w", err))
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	var result []goPackage
	for {
		var pkg goPackage
		if err := decoder.Decode(&pkg); err == io.EOF {
			break
		} else if err != nil {
			panic(err)
		}
		result = append(result, pkg)
	}
	return result
}

func main() {
	root, err := os.Getwd()
	if err != nil {
		panic(err)
	}
	ordinary := make(map[string]map[string]bool)
	for _, pkg := range packages(false) {
		ordinary[pkg.ImportPath] = make(map[string]bool)
		for _, file := range append(pkg.TestGoFiles, pkg.XTestGoFiles...) {
			ordinary[pkg.ImportPath][file] = true
		}
	}
	var result []integrationPackage
	for _, pkg := range packages(true) {
		rel, err := filepath.Rel(root, pkg.Dir)
		if err != nil || strings.HasPrefix(rel, "..") {
			panic("discovery escaped source checkout")
		}
		entry := integrationPackage{ImportPath: pkg.ImportPath, Path: "./" + filepath.ToSlash(rel), Files: make(map[string]string)}
		for _, file := range append(pkg.TestGoFiles, pkg.XTestGoFiles...) {
			if ordinary[pkg.ImportPath][file] {
				continue
			}
			path := filepath.Join(pkg.Dir, file)
			data, err := os.ReadFile(path)
			if err != nil {
				panic(err)
			}
			digest := sha256.Sum256(data)
			entry.Files[file] = hex.EncodeToString(digest[:])
			tree, err := parser.ParseFile(token.NewFileSet(), path, data, 0)
			if err != nil {
				panic(err)
			}
			for _, declaration := range tree.Decls {
				fn, ok := declaration.(*ast.FuncDecl)
				if !ok || fn.Recv != nil || !strings.HasPrefix(fn.Name.Name, "Test") || fn.Name.Name == "TestMain" || fn.Type.Params.NumFields() != 1 {
					continue
				}
				pointer, ok := fn.Type.Params.List[0].Type.(*ast.StarExpr)
				if !ok {
					continue
				}
				parameter, ok := pointer.X.(*ast.SelectorExpr)
				if ok && parameter.Sel.Name == "T" {
					entry.Tests = append(entry.Tests, fn.Name.Name)
				}
			}
		}
		if len(entry.Files) != 0 {
			sort.Strings(entry.Tests)
			result = append(result, entry)
		}
	}
	sort.Slice(result, func(i, j int) bool { return result[i].Path < result[j].Path })
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		panic(err)
	}
}
