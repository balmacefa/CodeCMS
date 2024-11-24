import express from "express";
import { NodeVM } from "vm2";

const app = express();
app.use(express.json());

const routes: Record<string, string> = {};

app.post("/register-route", (req, res) => {
  const { route, code } = req.body;

  if (!route || !code) {
    return res.status(400).json({ error: "Ruta y código son obligatorios." });
  }

  routes[route] = code;
  res.json({ message: `Ruta ${route} registrada correctamente.` });
});

app.all("*", (req, res) => {
  const route = req.path;
  const code = routes[route];

  if (!code) {
    return res.status(404).json({ error: "Ruta no encontrada." });
  }

  try {
    // Ejecutar el código TypeScript de forma segura
    const vm = new NodeVM({
      sandbox: { req }, // Puedes exponer más variables si lo deseas
    });

    const transpiledCode = require("typescript").transpile(code);
    const result = vm.run(transpiledCode);
    res.json({ result });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.listen(4000, () => {
  console.log("TypeScript Executor corriendo en http://localhost:4000");
});
