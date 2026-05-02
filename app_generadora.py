import io
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance
import cairosvg
import numpy as np

class AppCreator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Generador de Imagen 1920 VS. - Múltiples Enfrentamientos")
        self.geometry("800x700") 
        
        self.background_image_path = None
        self.logo_a_path = None
        self.logo_b_path = None
        self.enfrentamientos = []

        self.add_outline = tk.BooleanVar(value=False)
        self.outline_width = tk.IntVar(value=3)

        self.create_widgets()

    def create_widgets(self):
        # Frame para la selección de imagen de fondo
        bg_frame = tk.LabelFrame(self, text="Seleccionar Imagen de Fondo", padx=10, pady=10)
        bg_frame.pack(padx=10, pady=10, fill="x")

        self.bg_label = tk.Label(bg_frame, text="Fondo: No seleccionado")
        self.bg_label.pack(fill="x", pady=5)
        
        btn_bg = tk.Button(bg_frame, text="Seleccionar Imagen de Fondo", command=self.select_background_image)
        btn_bg.pack(fill="x", pady=5)

        # Frame para logos
        logo_frame = tk.LabelFrame(self, text="Seleccionar Logos", padx=10, pady=10)
        logo_frame.pack(padx=10, pady=10, fill="x")

        self.logo_a_label = tk.Label(logo_frame, text="Logo Equipo A: No seleccionado")
        self.logo_a_label.pack(fill="x", pady=5)
        btn_a = tk.Button(logo_frame, text="Seleccionar Logo A", command=self.select_logo_a)
        btn_a.pack(fill="x", pady=5)

        self.logo_b_label = tk.Label(logo_frame, text="Logo Equipo B: No seleccionado")
        self.logo_b_label.pack(fill="x", pady=5)
        btn_b = tk.Button(logo_frame, text="Seleccionar Logo B", command=self.select_logo_b)
        btn_b.pack(fill="x", pady=5)

        # Opciones avanzadas
        options_frame = tk.LabelFrame(self, text="Opciones Avanzadas", padx=10, pady=10)
        options_frame.pack(padx=10, pady=10, fill="x")

        outline_checkbox = tk.Checkbutton(options_frame, text="Agregar contorno blanco a los logos", 
                                        variable=self.add_outline)
        outline_checkbox.pack(anchor='w', pady=2)

        outline_scale = tk.Scale(options_frame, from_=1, to=8, orient='horizontal', 
                               label="Grosor del contorno", variable=self.outline_width)
        outline_scale.pack(fill="x", pady=2)

        self.auto_enhance_var = tk.BooleanVar()
        auto_enhance_checkbox = tk.Checkbutton(options_frame, 
                                             text="Mejorar automáticamente imagen de fondo", 
                                             variable=self.auto_enhance_var)
        auto_enhance_checkbox.pack(anchor='w', pady=2)

        # Añadir enfrentamiento
        enfrentamientos_frame = tk.LabelFrame(self, text="Añadir Enfrentamiento", padx=10, pady=10)
        enfrentamientos_frame.pack(padx=10, pady=10, fill="x")

        btn_add_enfrentamiento = tk.Button(enfrentamientos_frame, text="Añadir Enfrentamiento a la Lista", 
                                         command=self.add_enfrentamiento, bg="blue", fg="white")
        btn_add_enfrentamiento.pack(fill="x", pady=5)

        # Lista de enfrentamientos
        lista_frame = tk.LabelFrame(self, text="Enfrentamientos en Cola", padx=10, pady=10)
        lista_frame.pack(padx=10, pady=10, fill="both", expand=True)

        scrollbar = tk.Scrollbar(lista_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.enfrentamientos_listbox = tk.Listbox(lista_frame, yscrollcommand=scrollbar.set, height=8)
        self.enfrentamientos_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.config(command=self.enfrentamientos_listbox.yview)

        btn_frame = tk.Frame(lista_frame)
        btn_frame.pack(pady=5)
        btn_remove = tk.Button(btn_frame, text="Eliminar Seleccionado", command=self.remove_enfrentamiento)
        btn_remove.pack(side=tk.LEFT, padx=5)
        btn_clear = tk.Button(btn_frame, text="Limpiar Lista", command=self.clear_enfrentamientos)
        btn_clear.pack(side=tk.LEFT, padx=5)

        # Botón generar
        btn_generate = tk.Button(self, text="Generar Todas las Imágenes", command=self.generate_all_images, 
                               bg="green", fg="white", height=2)
        btn_generate.pack(pady=20, fill="x")

    def select_background_image(self):
        self.background_image_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.png *.jpeg")])
        if self.background_image_path:
            self.bg_label.config(text=f"Fondo: {self.background_image_path.split('/')[-1]}")

    def select_logo_a(self):
        self.logo_a_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.png *.jpeg *.svg")])
        if self.logo_a_path:
            self.logo_a_label.config(text=f"Logo Equipo A: {self.logo_a_path.split('/')[-1]}")

    def select_logo_b(self):
        self.logo_b_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.png *.jpeg *.svg")])
        if self.logo_b_path:
            self.logo_b_label.config(text=f"Logo Equipo B: {self.logo_b_path.split('/')[-1]}")

    def add_enfrentamiento(self):
        if not self.background_image_path:
            messagebox.showerror("Error", "Debes seleccionar una imagen para el fondo.")
            return
        if not self.logo_a_path or not self.logo_b_path:
            messagebox.showerror("Error", "Debes seleccionar ambos logos.")
            return

        equipo_a = self.logo_a_path.split('/')[-1].rsplit('.', 1)[0]
        equipo_b = self.logo_b_path.split('/')[-1].rsplit('.', 1)[0]
        
        enfrentamiento = {
            'background': self.background_image_path,
            'logo_a': self.logo_a_path,
            'logo_b': self.logo_b_path,
            'equipo_a': equipo_a,
            'equipo_b': equipo_b,
            'add_outline': self.add_outline.get(),
            'outline_width': self.outline_width.get(),
            'auto_enhance': self.auto_enhance_var.get()
        }
        
        self.enfrentamientos.append(enfrentamiento)
        display_text = f"{equipo_a} vs {equipo_b}"
        self.enfrentamientos_listbox.insert(tk.END, display_text)

    def remove_enfrentamiento(self):
        selection = self.enfrentamientos_listbox.curselection()
        if selection:
            index = selection[0]
            self.enfrentamientos_listbox.delete(index)
            del self.enfrentamientos[index]
        else:
            messagebox.showwarning("Advertencia", "Selecciona un enfrentamiento para eliminar.")

    def clear_enfrentamientos(self):
        self.enfrentamientos.clear()
        self.enfrentamientos_listbox.delete(0, tk.END)
        messagebox.showinfo("Información", "Lista de enfrentamientos limpiada.")

    def generate_all_images(self):
        if not self.enfrentamientos:
            messagebox.showerror("Error", "No hay enfrentamientos en la lista.")
            return

        save_folder = filedialog.askdirectory(title="Selecciona carpeta para guardar las imágenes")
        if not save_folder:
            return

        total_enfrentamientos = len(self.enfrentamientos)
        successful_generations = 0
        errores_enfrentamientos = []

        progress_window = tk.Toplevel(self)
        progress_window.title("Generando Imágenes")
        progress_window.geometry("400x100")
        progress_window.transient(self)
        progress_window.grab_set()

        progress_label = tk.Label(progress_window, text="Iniciando generación...")
        progress_label.pack(pady=10)

        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_window, variable=progress_var, maximum=total_enfrentamientos)
        progress_bar.pack(pady=10, padx=20, fill="x")

        for i, enfrentamiento in enumerate(self.enfrentamientos):
            progress_label.config(text=f"Generando: {enfrentamiento['equipo_a']} vs {enfrentamiento['equipo_b']}")
            progress_var.set(i)
            self.update()

            try:
                self.generate_single_enfrentamiento(enfrentamiento, save_folder)
                successful_generations += 1
            except Exception as e:
                errores_enfrentamientos.append(f"{enfrentamiento['equipo_a']} vs {enfrentamiento['equipo_b']}: {str(e)}")

        progress_window.destroy()

        mensaje = f"✅ {successful_generations} de {total_enfrentamientos} imágenes generadas."
        if errores_enfrentamientos:
            mensaje += f"\n\n❌ Errores en {len(errores_enfrentamientos)} archivo(s):\n"
            for err in errores_enfrentamientos[:3]:
                mensaje += f"• {err}\n"
            if len(errores_enfrentamientos) > 3:
                mensaje += f"• ... y {len(errores_enfrentamientos)-3} más."

        messagebox.showinfo("Resultado", mensaje) if successful_generations > 0 else messagebox.showerror("Error", mensaje)

    def generate_single_enfrentamiento(self, enfrentamiento, save_folder):
        equipo_a = enfrentamiento['equipo_a']
        equipo_b = enfrentamiento['equipo_b']
        background_path = enfrentamiento['background']
        logo_a_path = enfrentamiento['logo_a']
        logo_b_path = enfrentamiento['logo_b']
        add_outline = enfrentamiento['add_outline']
        outline_width = enfrentamiento['outline_width']
        auto_enhance = enfrentamiento.get('auto_enhance', False)

        resolutions = [
            (1920, 1080, (476, 666), (1440, 666), int(450 * 1920 / 1920), int(130 * 1920 / 1920), "1920x1080"),
            (3840, 2160, (952, 1332), (2880, 1332), int(450 * 3840 / 1920), int(130 * 3840 / 1920), "3840x2160"),
            (480, 720, (120, 230), (360, 515), 177, 60, "480x720"),
        ]

        for width, height, logo_a_pos, logo_b_pos, logo_size, font_size, res_str in resolutions:
            # Cargar fondo
            bg_image = Image.open(background_path).convert("RGB")
            bg_w, bg_h = bg_image.size
            aspect_bg = bg_w / bg_h
            aspect_out = width / height

            if aspect_bg > aspect_out:
                new_w = int(height * aspect_bg)
                new_h = height
            else:
                new_w = width
                new_h = int(width / aspect_bg)
            
            bg_image = bg_image.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - width) // 2
            top = (new_h - height) // 2
            right = left + width
            bottom = top + height
            bg_image = bg_image.crop((left, top, right, bottom))

            blur_radius = {1920: 11.3, 3840: 20, 480: 8.1}.get(width, 10)
            bg_image = bg_image.filter(ImageFilter.GaussianBlur(blur_radius))
            
            if auto_enhance:
                bg_image = self.auto_enhance_background(bg_image)

            image = bg_image
            draw = ImageDraw.Draw(image)

            # Cargar logos
            logo_a = self.load_and_convert_logo(logo_a_path)
            logo_a = self.resize_logo(logo_a, max_size=logo_size, add_outline=add_outline, outline_width=outline_width)
            x_a = logo_a_pos[0] - logo_a.width // 2
            y_a = logo_a_pos[1] - logo_a.height // 2
            image.paste(logo_a, (x_a, y_a), logo_a)

            logo_b = self.load_and_convert_logo(logo_b_path)
            logo_b = self.resize_logo(logo_b, max_size=logo_size, add_outline=add_outline, outline_width=outline_width)
            x_b = logo_b_pos[0] - logo_b.width // 2
            y_b = logo_b_pos[1] - logo_b.height // 2
            image.paste(logo_b, (x_b, y_b), logo_b)

            # Texto "VS." con fuente Roboto Black Italic
            try:
                # Intentar cargar Roboto Black Italic
                font = ImageFont.truetype("Roboto-BlackItalic.ttf", font_size)
            except IOError:
                try:
                    # Fallback: Roboto Black
                    font = ImageFont.truetype("Roboto-Black.ttf", font_size)
                except IOError:
                    try:
                        # Fallback: Roboto Bold Italic
                        font = ImageFont.truetype("Roboto-BoldItalic.ttf", font_size)
                    except IOError:
                        try:
                            # Fallback: Impact Italic
                            font = ImageFont.truetype("Impact-Italic.ttf", font_size)
                        except IOError:
                            try:
                                # Fallback: Helvetica Bold Oblique (macOS)
                                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
                            except IOError:
                                print("Fuente Roboto no encontrada. Usando predeterminada.")
                                font = ImageFont.load_default()

            text = "VS."
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            center_x = (width - text_w) // 2
            center_y = (height - text_h) // 2

            # Ajustar offset según resolución para mejor centrado
            if width == 480:  # Para 480x720, centrar más precisamente
                offset_percent = int(height * 0.02)  # Solo 2% hacia abajo
            else:  # Para otras resoluciones mantener 5%
                offset_percent = int(height * 0.05)
            
            text_y = center_y + offset_percent

            # Dibujar texto en blanco
            draw.text((center_x, text_y), text, fill="white", font=font)

            filename = f"{equipo_a} vs {equipo_b} - {res_str}.jpg"
            save_path = f"{save_folder}/{filename}"
            image.convert("RGB").save(save_path, "JPEG", quality=97)

    def load_and_convert_logo(self, file_path):
        if file_path.lower().endswith('.svg'):
            try:
                png_data = cairosvg.svg2png(url=file_path)
                return Image.open(io.BytesIO(png_data)).convert("RGBA")
            except Exception:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    cleaned = content.replace('&ns_extend;', '').replace('&ns_ai;', '')
                    png_data = cairosvg.svg2png(bytestring=cleaned.encode('utf-8'))
                    return Image.open(io.BytesIO(png_data)).convert("RGBA")
                except Exception:
                    raise Exception(f"No se pudo procesar el SVG: {file_path}")
        else:
            try:
                return Image.open(file_path).convert("RGBA")
            except Exception as e:
                raise Exception(f"No se pudo cargar la imagen: {e}")

    def resize_logo(self, logo_image, max_size=450, add_outline=False, outline_width=3):
        w, h = logo_image.size
        if w > h:
            new_w = max_size
            new_h = int(h * (max_size / w))
        else:
            new_h = max_size
            new_w = int(w * (max_size / h))
        logo_resized = logo_image.resize((new_w, new_h), Image.LANCZOS)

        if not add_outline:
            return logo_resized

        scale_factor = 4
        temp_logo = logo_resized.resize((new_w * scale_factor, new_h * scale_factor), Image.LANCZOS)
        alpha = temp_logo.split()[-1] if temp_logo.mode == 'RGBA' else Image.new('L', temp_logo.size, 255)

        # Crear padding más generoso para evitar recorte
        # El blur necesita espacio extra, especialmente para contornos gruesos
        blur_radius = outline_width * scale_factor
        extra_padding = blur_radius * 2  # Espacio adicional para el blur
        padding = int(outline_width * scale_factor * 2.5) + extra_padding
        
        # Crear canvas expandido para el alpha antes del blur
        expanded_w = temp_logo.width + 2 * padding
        expanded_h = temp_logo.height + 2 * padding
        expanded_alpha = Image.new('L', (expanded_w, expanded_h), 0)
        
        # Pegar el alpha original en el centro del canvas expandido
        alpha_pos = ((expanded_w - alpha.width) // 2, (expanded_h - alpha.height) // 2)
        expanded_alpha.paste(alpha, alpha_pos)
        
        # Aplicar filtros al alpha expandido
        dilated = expanded_alpha.filter(ImageFilter.MaxFilter(3))
        blurred = dilated.filter(ImageFilter.GaussianBlur(blur_radius))

        # Crear resultado final con el mismo tamaño que el alpha expandido
        result = Image.new("RGBA", (expanded_w, expanded_h), (0, 0, 0, 0))
        
        # El blur ya está en el tamaño correcto, usar directamente
        result.paste((255, 255, 255), (0, 0), mask=blurred)

        # Pegar logo original en el centro
        logo_pos = ((expanded_w - temp_logo.width) // 2, (expanded_h - temp_logo.height) // 2)
        result.paste(temp_logo, logo_pos, temp_logo)

        # Escalar de vuelta al tamaño final
        final_size = (expanded_w // scale_factor, expanded_h // scale_factor)
        return result.resize(final_size, Image.LANCZOS)

    def auto_enhance_background(self, img, level='moderate'):
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img = ImageOps.equalize(img)
        img = ImageEnhance.Contrast(img).enhance(1.1)
        img = ImageEnhance.Brightness(img).enhance(1.05)
        img = ImageEnhance.Color(img).enhance(1.1)
        img = ImageEnhance.Sharpness(img).enhance(1.1)
        return img

if __name__ == "__main__":
    app = AppCreator()
    app.mainloop()