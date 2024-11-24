package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"os"
	"os/exec"
)

type Route struct {
	Route string `json:"route"`
	Code  string `json:"code"`
}

var routes = make(map[string]string)

func registerRoute(w http.ResponseWriter, r *http.Request) {
	var req Route
	body, _ := ioutil.ReadAll(r.Body)
	json.Unmarshal(body, &req)

	routes[req.Route] = req.Code
	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, "Ruta registrada: %s", req.Route)
}

func handleDynamicRoute(w http.ResponseWriter, r *http.Request) {
	code, exists := routes[r.URL.Path]
	if !exists {
		http.Error(w, "Ruta no encontrada", http.StatusNotFound)
		return
	}

	// Guardar código en un archivo temporal
	tmpFile := "temp.go"
	_ = ioutil.WriteFile(tmpFile, []byte(code), 0644)

	// Ejecutar código con `go run`
	cmd := exec.Command("go", "run", tmpFile)
	output, err := cmd.CombinedOutput()
	if err != nil {
		http.Error(w, string(output), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Write(output)
}

func main() {
	http.HandleFunc("/register-route", registerRoute)
	http.HandleFunc("/", handleDynamicRoute)

	fmt.Println("Go Executor corriendo en http://localhost:6000")
	http.ListenAndServe(":6000", nil)
}
