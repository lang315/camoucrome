package rodclient

import (
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"reflect"
	"sort"
	"strings"
	"testing"
)

// The vetted surface, exactly. Adding a method here is a review decision.
// AddInitScript (Task 4): counterpart of playwright's add_init_script, sends
// only Page.addScriptToEvaluateOnNewDocument; the script runs in the MAIN world
// by design (the caller wrote it), so the contract probe can measure C6.
var allowedPageMethods = []string{"AddInitScript", "Attribute", "Click", "Close", "Cookies", "Eval", "Goto",
	"Screenshot", "Text", "Type", "WaitForSelector"}

func TestPageSurfaceIsVetted(t *testing.T) {
	pt := reflect.TypeOf(&Page{})
	var got []string
	for i := 0; i < pt.NumMethod(); i++ {
		got = append(got, pt.Method(i).Name)
	}
	sort.Strings(got)
	if !reflect.DeepEqual(got, allowedPageMethods) {
		t.Fatalf("exported Page methods (%d) differ from the vetted set:\n got %v\nwant %v", len(got), got, allowedPageMethods)
	}
	st := pt.Elem()
	if st.Kind() != reflect.Struct {
		t.Fatalf("Page is %v, not a struct wrapper", st.Kind())
	}
	for i := 0; i < st.NumField(); i++ {
		if f := st.Field(i); f.IsExported() || f.Anonymous {
			t.Errorf("Page field %s must be unexported and not embedded", f.Name)
		}
	}
}

var allowedExported = []string{"Browser", "Cookie", "Launch", "Page", "WaitLoad", "WaitNetworkIdle", "WaitUntil"}

// Top-level exported identifiers of the package, parsed from source so that a
// future func RodPage(*Page) *rod.Page fails here.
func TestExportedIdentifiersAreVetted(t *testing.T) {
	fs := token.NewFileSet()
	pkgs, err := parser.ParseDir(fs, ".", func(fi os.FileInfo) bool { return !strings.HasSuffix(fi.Name(), "_test.go") }, 0)
	if err != nil {
		t.Fatal(err)
	}
	var got []string
	for _, f := range pkgs["rodclient"].Files {
		for _, d := range f.Decls {
			switch d := d.(type) {
			case *ast.FuncDecl:
				if d.Recv == nil && d.Name.IsExported() {
					got = append(got, d.Name.Name)
				}
			case *ast.GenDecl:
				for _, sp := range d.Specs {
					switch sp := sp.(type) {
					case *ast.TypeSpec:
						if sp.Name.IsExported() {
							got = append(got, sp.Name.Name)
						}
					case *ast.ValueSpec:
						for _, n := range sp.Names {
							if n.IsExported() {
								got = append(got, n.Name)
							}
						}
					}
				}
			}
		}
	}
	sort.Strings(got)
	if !reflect.DeepEqual(got, allowedExported) {
		t.Fatalf("exported identifiers\n got %v\nwant %v", got, allowedExported)
	}
}

func TestBrowserSurface(t *testing.T) {
	bt := reflect.TypeOf(&Browser{})
	var got []string
	for i := 0; i < bt.NumMethod(); i++ {
		got = append(got, bt.Method(i).Name)
	}
	if want := []string{"Argv", "Close", "NewPage", "OnSend"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("Browser methods %v, want %v", got, want)
	}
}
