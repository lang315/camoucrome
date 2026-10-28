package rodclient

import (
	"reflect"
	"sort"
	"testing"
)

// The vetted surface, exactly. Adding a method here is a review decision.
var allowedPageMethods = []string{"Attribute", "Click", "Close", "Cookies", "Eval", "Goto",
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
