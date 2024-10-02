import tkinter as tk
import requests
import threading
import queue
from datetime import datetime

class MinimapApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Minimap")

        # Set initial window size
        self.canvas_width = 800
        self.canvas_height = 400

        # Create a canvas with no background color
        self.canvas = tk.Canvas(self.root, width=self.canvas_width, height=self.canvas_height, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Set the chroma key color (e.g., bright pink)
        self.chroma_key_color = '#FF69B4'  # Bright pink

        # Region bounds
        self.region_min_x = -3364
        self.region_max_x = 3300
        self.region_min_y = 24736
        self.region_max_y = 29701

        # Queue to communicate between the background thread and the main thread
        self.queue = queue.Queue()

        # Create a persistent session
        self.session = requests.Session()

        # Initialize selected ball index
        self.selected_ball_index = None

        # Start the data fetching thread
        self.running = True

        # Fetch the data initially once and show ball selection window
        self.initial_fetch_thread = threading.Thread(target=self.fetch_data_once)
        self.initial_fetch_thread.daemon = True
        self.initial_fetch_thread.start()

        # Bind resize event to adjust the canvas size
        self.root.bind('<Configure>', self.on_resize)

        # Create and show the persistent ball selection window
        self.ball_selection_window = None  # Initialize the ball selection window
        self.show_ball_selection_window()   # Show the ball selection window without waiting for data

    def fetch_data_once(self):
        """Fetch data once at the start."""
        try:
            response = self.session.get('http://localhost:5420/state')
            if response.status_code == 200:
                data = response.json()
                balls = data.get('balls', [])
                if balls:
                    # Populate the ball selection window with the fetched data
                    self.update_ball_selection_window(balls)
        except Exception as e:
            print("Error fetching initial data:", e)

    def show_ball_selection_window(self):
        """Show a window for the user to select a ball."""
        self.ball_selection_window = tk.Toplevel(self.root)
        self.ball_selection_window.title("Select a Ball")

        label = tk.Label(self.ball_selection_window, text="Choose a ball to track:")
        label.pack(pady=10)

        self.ball_listbox = tk.Listbox(self.ball_selection_window)
        self.ball_listbox.pack(pady=10, padx=10)

        # Handle ball selection
        def on_select(event):
            selected = self.ball_listbox.curselection()
            if selected:
                self.selected_ball_index = selected[0]
                self.start_real_time_update()  # Start real-time updates

        self.ball_listbox.bind('<<ListboxSelect>>', on_select)  # Bind selection event

        self.update_ball_selection_window([])  # Initialize with an empty list until data is fetched

    def update_ball_selection_window(self, balls):
        """Populate the ball selection window with ball data."""
        self.ball_listbox.delete(0, tk.END)  # Clear the listbox
        for i, ball in enumerate(balls):
            self.ball_listbox.insert(tk.END, f"Ball {i + 1}: x={ball['transform']['position']['x']}, y={ball['transform']['position']['y']}")

    def start_real_time_update(self):
        """Start fetching data in real-time after ball selection."""
        self.update_thread = threading.Thread(target=self.fetch_data)
        self.update_thread.daemon = True
        self.update_thread.start()

        # Start the UI update loop
        self.update_minimap()

    def fetch_data(self):
        """Fetch data continuously from the server and put it in the queue."""
        while self.running:
            try:
                response = self.session.get('http://localhost:5420/state')
                if response.status_code == 200:
                    data = response.json()
                    # Put the player and ball data in the queue
                    self.queue.put({
                        'players': data.get('players', []),
                        'balls': data.get('balls', [])
                    })
                else:
                    self.queue.put(None)
            except Exception as e:
                self.queue.put(None)

    def update_minimap(self):
        """Check the queue and update the minimap if there's new data."""
        try:
            # Try to get data from the queue
            data = self.queue.get_nowait()
            if data is not None:
                players = data.get('players', [])
                balls = data.get('balls', [])

                if self.selected_ball_index is not None and len(balls) > self.selected_ball_index:
                    # Update the canvas with players and the selected ball
                    selected_ball = balls[self.selected_ball_index]
                    self.update_canvas(players, selected_ball)

                # Print the update to the console with a timestamp
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
                print(f"[{timestamp}] Minimap updated with selected ball")
        except queue.Empty:
            # No data in the queue
            pass

        # Schedule the next update (set to near real-time, 1ms for constant updates)
        self.root.after(1, self.update_minimap)  # Call `update_minimap` again every 1ms

    def update_canvas(self, players, ball):
        """Update the canvas with the player data and the selected ball."""
        # Clear the canvas and redraw the background color
        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 0, self.canvas_width, self.canvas_height, fill=self.chroma_key_color, outline=self.chroma_key_color)

        # Set sizes for player and ball dots
        player_dot_radius = 10  # Player dot size
        ball_dot_radius = 15    # Ball dot size

        # Draw players
        for player in players:
            # Extract player position
            position = player['root']['position']
            x, y = position['x'], position['y']

            # Extract team color index
            team_color_index = player.get('teamColorIndex', -1)

            # Check if player is within the specified region
            if self.region_min_x <= x <= self.region_max_x and self.region_min_y <= y <= self.region_max_y:
                # Check the team color index and decide the color
                if team_color_index == -1:
                    continue  # Skip rendering this player
                elif team_color_index == 0:
                    color = 'red'
                elif team_color_index == 4:
                    color = 'blue'
                else:
                    color = 'black'  # Default color if index is not recognized

                # Normalize coordinates for the canvas
                canvas_x = self.normalize_coordinate(x, self.region_min_x, self.region_max_x, self.canvas_width)
                canvas_y = self.normalize_coordinate(y, self.region_min_y, self.region_max_y, self.canvas_height)

                # Draw a circle to represent the player
                self.canvas.create_oval(canvas_x - player_dot_radius, canvas_y - player_dot_radius, 
                                        canvas_x + player_dot_radius, canvas_y + player_dot_radius, fill=color)
                self.canvas.create_text(canvas_x, canvas_y - player_dot_radius - 10, text=player['playerName'], fill='black')

        # Draw the selected ball
        position = ball['transform']['position']
        x, y = position['x'], position['y']

        # Check if the ball is within the specified region
        if self.region_min_x <= x <= self.region_max_x and self.region_min_y <= y <= self.region_max_y:
            # Normalize coordinates for the canvas
            canvas_x = self.normalize_coordinate(x, self.region_min_x, self.region_max_x, self.canvas_width)
            canvas_y = self.normalize_coordinate(y, self.region_min_y, self.region_max_y, self.canvas_height)

            # Draw a green circle to represent the ball
            self.canvas.create_oval(canvas_x - ball_dot_radius, canvas_y - ball_dot_radius, 
                                    canvas_x + ball_dot_radius, canvas_y + ball_dot_radius, fill='green')

    def normalize_coordinate(self, value, min_val, max_val, scale):
        """Normalize a coordinate value to fit within the canvas scale.""" 
        return ((value - min_val) / (max_val - min_val)) * scale

    def on_resize(self, event):
        """Handle window resizing.""" 
        self.canvas_width = event.width
        self.canvas_height = event.height
        self.canvas.config(width=self.canvas_width, height=self.canvas_height)
        self.update_canvas([], [])  # Redraw canvas on resize

    def on_closing(self):
        """Handle the closing of the application.""" 
        self.running = False
        if hasattr(self, 'update_thread'):
            self.update_thread.join()
        self.session.close()  # Close the session when the app is closed
        self.root.destroy()

def run_app():
    root = tk.Tk()
    app = MinimapApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)  # Handle window closing
    root.mainloop()

# Run the application
run_app()
