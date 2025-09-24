# 📚 Mindtrace UI Component Library

Welcome to the **Mindtrace UI Component Library**!  
This repo contains reusable, themeable UI components built with [Reflex](https://reflex.dev).  
It includes a **storybook-like playground** for previewing components, plus design tokens and themes.

---

## ✨ Features

- 🧩 Modular UI components (breadcrumbs, alerts, accordions, inputs, tables, etc.)
- 🎛️ Storybook-inspired **Playground** with live previews + controls
- 🎨 Theming & Tokens for consistent design
- ⚡ Powered by **Reflex** and `uv` runner for a smooth workflow

---

## 🚀 Getting Started

### 1. Install dependencies
We recommend using [`uv`](https://github.com/astral-sh/uv) for environment management.

```bash
uv pip install -r requirements.txt
```

### 2. Run the Playground
Start the Reflex dev server and open the **storybook-like UI**:

```bash
uv run reflex run
```

Visit: [http://localhost:3000](http://localhost:3000)

---

## 📂 Project Structure

```
mindtrace/ui/
│── components/         # Core UI components
│   ├── layout/
│   ├── navigation/
│   ├── inputs/
│   ├── data/
│   ├── feedback/
│   └── empty/
│
│── playground/         # Storybook-like preview app
│   ├── stories_registry.py
│   └── storybook.py
│
│── themes/             # Tokens and theme overrides
│── rxconfig.py         # Reflex config
```

---

## 🛠️ Usage

### Add a new Component
1. Create your component in `components/`  
2. Add a state class (if needed)  
3. Register a **story** in `stories_registry.py`:
   ```python
   STORY_MYCOMP = {
       "id": "my_component",
       "name": "My Component",
       "preview": story_mycomp_preview,
       "controls": story_mycomp_controls,
       "code": _story_mycomp_code,
   }
   ```
4. Add it to `STORIES` list  
5. It will automatically appear in the Playground sidebar 🎉

---

## 🎨 Theming & Tokens

- Global theme variables live under `themes/`
- Use design tokens (`colors`, `spacing`, `typography`) for consistency
- Example:
  ```python
  import reflex as rx
  from mindtrace.ui.tokens import C

  def my_button():
      return rx.button("Click Me", background=C["primary"])
  ```

---

## 📖 Storybook Playground

The **Playground app** lets you:
- Preview each component in isolation
- Change props live with controls
- Copy code snippets directly into your app

---

## 🏗️ Build for Export

When you want to export the app (e.g., deploy docs or demos):

```bash
uv run reflex export
```

---

## 🤝 Contributing

- Keep components **stateless** when possible  
- Use `rx.foreach`, `rx.cond` with State Vars instead of Python loops/ifs  
- Write **stories** for each new component  
- Follow the existing folder structure  

---

## 🧑‍💻 Authors

Mindtrace Team 🚀

---

## 📜 License

MIT License © 2025 Mindtrace
