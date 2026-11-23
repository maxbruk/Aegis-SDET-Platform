package main

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/lib/pq"
)

type MetricsRegistry struct {
	mu                sync.RWMutex
	httpCounts        map[string]int64
	httpDurationSum   map[string]float64
	httpDurationCount map[string]int64
	checkoutResults   map[string]int64
	totalExecutions   int64
	uniqueTests       int64
	passRate          float64
	flakyRate         float64
	p50Ms             float64
	p95Ms             float64
	webVitals         map[string]float64
	failureCategories map[string]int64
}

func newMetricsRegistry() *MetricsRegistry {
	return &MetricsRegistry{
		httpCounts:        make(map[string]int64),
		httpDurationSum:   make(map[string]float64),
		httpDurationCount: make(map[string]int64),
		checkoutResults:   make(map[string]int64),
		webVitals:         make(map[string]float64),
		failureCategories: make(map[string]int64),
	}
}

type Server struct {
	db        *sql.DB
	jwtSecret []byte
	metrics   *MetricsRegistry
}

type UserDTO struct {
	ID        int    `json:"id"`
	Name      string `json:"name"`
	Email     string `json:"email"`
	Role      string `json:"role"`
	CreatedAt string `json:"created_at"`
}

type AuthResponse struct {
	Token string  `json:"token"`
	User  UserDTO `json:"user"`
}

type ProductDTO struct {
	ID          int     `json:"id"`
	Name        string  `json:"name"`
	Description string  `json:"description"`
	Price       float64 `json:"price"`
	Stock       int     `json:"stock"`
	Category    string  `json:"category"`
	CreatedAt   string  `json:"created_at"`
}

type CartItemDTO struct {
	ProductID   int     `json:"product_id"`
	ProductName string  `json:"product_name"`
	Name        string  `json:"name"`
	Price       float64 `json:"price"`
	Quantity    int     `json:"quantity"`
	Subtotal    float64 `json:"subtotal"`
	Stock       int     `json:"stock"`
}

type CartResponse struct {
	Items      []CartItemDTO `json:"items"`
	TotalItems int           `json:"total_items"`
	Subtotal   float64       `json:"subtotal"`
	Tax        float64       `json:"tax"`
	Total      float64       `json:"total"`
}

type OrderItemDTO struct {
	ProductID   int     `json:"product_id"`
	ProductName string  `json:"product_name"`
	Quantity    int     `json:"quantity"`
	UnitPrice   float64 `json:"unit_price"`
	TotalPrice  float64 `json:"total_price"`
}

type OrderResponse struct {
	ID             int            `json:"id"`
	OrderID        string         `json:"order_id"`
	UserID         *int           `json:"user_id,omitempty"`
	Status         string         `json:"status"`
	TotalAmount    float64        `json:"total_amount"`
	ItemsCount     int            `json:"items_count"`
	IdempotencyKey string         `json:"idempotency_key,omitempty"`
	CreatedAt      string         `json:"created_at"`
	Items          []OrderItemDTO `json:"items"`
}

type Claims struct {
	Sub   int    `json:"sub"`
	Email string `json:"email"`
	Name  string `json:"name"`
	Role  string `json:"role"`
	Exp   int64  `json:"exp"`
}

func main() {
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://aegis:aegis_password@localhost:5432/aegis_store?sslmode=disable"
	}

	jwtSecret := os.Getenv("JWT_SECRET")
	if jwtSecret == "" {
		jwtSecret = "aegis-dev-secret-key"
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "3000"
	}

	db, err := connectWithRetry(dbURL, 20*time.Second)
	if err != nil {
		log.Fatalf("failed to connect to postgres: %v", err)
	}
	defer db.Close()

	if err := migrateAndSeed(db); err != nil {
		log.Fatalf("failed to migrate/seed database: %v", err)
	}

	srv := &Server{
		db:        db,
		jwtSecret: []byte(jwtSecret),
		metrics:   newMetricsRegistry(),
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", srv.handleHealth)
	mux.HandleFunc("/metrics", srv.handleMetrics)
	mux.HandleFunc("/api/v1/telemetry/ingest", srv.handleTelemetryIngest)
	mux.HandleFunc("/api/v1/auth/register", srv.handleRegister)
	mux.HandleFunc("/api/v1/auth/login", srv.handleLogin)
	mux.HandleFunc("/api/v1/auth/me", srv.handleMe)
	mux.HandleFunc("/api/v1/users/", srv.handleUserByID)
	mux.HandleFunc("/api/v1/products", srv.handleProducts)
	mux.HandleFunc("/api/v1/products/", srv.handleProductByID)
	mux.HandleFunc("/api/v1/cart", srv.handleCart)
	mux.HandleFunc("/api/v1/cart/items", srv.handleCartItems)
	mux.HandleFunc("/api/v1/cart/items/", srv.handleCartItemByProductID)
	mux.HandleFunc("/api/v1/orders/checkout", srv.handleCheckout)
	mux.HandleFunc("/api/v1/orders", srv.handleOrders)
	mux.HandleFunc("/api/v1/orders/", srv.handleOrderByID)

	handler := corsMiddleware(srv.metricsMiddleware(mux))
	httpServer := &http.Server{
		Addr:              ":" + port,
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
	}

	log.Printf("AEGIS Store Backend listening on :%s", port)
	if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("server error: %v", err)
	}
}

func connectWithRetry(dbURL string, timeout time.Duration) (*sql.DB, error) {
	deadline := time.Now().Add(timeout)
	var lastErr error
	for time.Now().Before(deadline) {
		db, err := sql.Open("postgres", dbURL)
		if err == nil {
			db.SetMaxOpenConns(25)
			db.SetMaxIdleConns(10)
			if pingErr := db.Ping(); pingErr == nil {
				return db, nil
			} else {
				lastErr = pingErr
				_ = db.Close()
			}
		} else {
			lastErr = err
		}
		time.Sleep(500 * time.Millisecond)
	}
	return nil, fmt.Errorf("database connection timed out: %w", lastErr)
}

func migrateAndSeed(db *sql.DB) error {
	schema := `
	CREATE TABLE IF NOT EXISTS users (
		id SERIAL PRIMARY KEY,
		name TEXT NOT NULL,
		email TEXT UNIQUE NOT NULL,
		password_hash TEXT NOT NULL,
		role TEXT NOT NULL DEFAULT 'customer',
		created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
	);

	CREATE TABLE IF NOT EXISTS products (
		id SERIAL PRIMARY KEY,
		name TEXT NOT NULL,
		description TEXT NOT NULL DEFAULT '',
		price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
		stock INT NOT NULL CHECK (stock >= 0),
		category TEXT NOT NULL,
		created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
	);

	CREATE TABLE IF NOT EXISTS cart_items (
		user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
		product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
		quantity INT NOT NULL CHECK (quantity > 0),
		PRIMARY KEY (user_id, product_id)
	);

	CREATE TABLE IF NOT EXISTS orders (
		id SERIAL PRIMARY KEY,
		order_id TEXT UNIQUE NOT NULL,
		user_id INT REFERENCES users(id) ON DELETE SET NULL,
		shipping_address TEXT NOT NULL,
		payment_method TEXT NOT NULL DEFAULT 'credit_card',
		status TEXT NOT NULL DEFAULT 'confirmed',
		total_amount NUMERIC(10, 2) NOT NULL,
		items_count INT NOT NULL,
		idempotency_key TEXT UNIQUE,
		created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
	);

	CREATE TABLE IF NOT EXISTS order_items (
		id SERIAL PRIMARY KEY,
		order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
		product_id INT NOT NULL,
		product_name TEXT NOT NULL,
		quantity INT NOT NULL,
		unit_price NUMERIC(10, 2) NOT NULL,
		total_price NUMERIC(10, 2) NOT NULL
	);

	CREATE TABLE IF NOT EXISTS test_execution_telemetry (
		id SERIAL PRIMARY KEY,
		run_id TEXT NOT NULL,
		test_id TEXT NOT NULL,
		suite TEXT NOT NULL DEFAULT 'all',
		status TEXT NOT NULL,
		duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
		browser TEXT NOT NULL DEFAULT 'chromium',
		worker TEXT NOT NULL DEFAULT 'main',
		environment TEXT NOT NULL DEFAULT 'local',
		failure_category TEXT NOT NULL DEFAULT '',
		ttfb_ms DOUBLE PRECISION,
		fcp_ms DOUBLE PRECISION,
		lcp_ms DOUBLE PRECISION,
		cls_score DOUBLE PRECISION,
		inp_ms DOUBLE PRECISION,
		js_heap_mb DOUBLE PRECISION,
		created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
		UNIQUE (run_id, test_id, worker)
	);
	`
	if _, err := db.Exec(schema); err != nil {
		return err
	}

	adminHash, err := hashPassword("password123")
	if err != nil {
		return err
	}
	customerHash, err := hashPassword("password123")
	if err != nil {
		return err
	}

	_, err = db.Exec(`
		INSERT INTO users (name, email, password_hash, role)
		VALUES
			('System Admin', 'admin@example.com', $1, 'admin'),
			('Alex Taylor', 'customer@example.com', $2, 'customer')
		ON CONFLICT (email) DO NOTHING;
	`, adminHash, customerHash)
	if err != nil {
		return err
	}

	seedProducts := []struct {
		id          int
		name        string
		category    string
		price       float64
		stock       int
		description string
	}{
		{1, "Apex Pro Mechanical Keyboard", "Electronics", 149.99, 15, "Aircraft-grade aluminum frame, hot-swappable tactile switches, and PBT double-shot keycaps."},
		{2, "Precision Ergonomic Mouse", "Electronics", 79.99, 24, "4000 DPI optical sensor, ultra-low latency wireless, and contoured thumb rest."},
		{3, "Studio Reference Headphones", "Audio", 249.99, 8, "Open-back planar magnetic drivers delivering ultra-wide soundstage and neutral frequency response."},
		{4, "USB-C Braided Thunderbolt Cable", "Accessories", 29.99, 50, "40Gbps data throughput and 100W Power Delivery with reinforced nylon braiding."},
		{5, "Solid Walnut Desk Mat (Extended)", "Workspace", 64.99, 12, "Eco-friendly natural wool felt top with non-slip cork base and beveled edge detailing."},
		{6, "Ultra-Fast NVMe SSD Enclosure", "Electronics", 54.99, 18, "Tool-free aluminum thermal enclosure supporting up to 10Gbps USB 3.2 Gen 2 transfer speeds."},
	}

	for _, p := range seedProducts {
		_, err := db.Exec(`
			INSERT INTO products (id, name, description, price, stock, category)
			VALUES ($1, $2, $3, $4, $5, $6)
			ON CONFLICT (id) DO NOTHING;
		`, p.id, p.name, p.description, p.price, p.stock, p.category)
		if err != nil {
			return err
		}
	}

	_, err = db.Exec(`SELECT setval('products_id_seq', COALESCE((SELECT MAX(id) FROM products), 1), true);`)
	return err
}

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, Idempotency-Key, Accept")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	if err := s.db.PingContext(ctx); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"status":   "unhealthy",
			"database": "unreachable",
		})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"status":   "healthy",
		"database": "healthy",
	})
}

func (s *Server) handleRegister(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}

	var req struct {
		Name     string `json:"name"`
		Username string `json:"username"`
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_JSON", "invalid request payload")
		return
	}

	name := strings.TrimSpace(req.Name)
	if name == "" {
		name = strings.TrimSpace(req.Username)
	}
	email := strings.ToLower(strings.TrimSpace(req.Email))
	if name == "" || !strings.Contains(email, "@") || len(req.Password) < 8 {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "valid name, email, and password (>= 8 chars) are required")
		return
	}

	pwHash, err := hashPassword(req.Password)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to hash password")
		return
	}

	var user UserDTO
	var createdAt time.Time
	err = s.db.QueryRowContext(
		r.Context(),
		`INSERT INTO users (name, email, password_hash, role)
		 VALUES ($1, $2, $3, 'customer')
		 RETURNING id, name, email, role, created_at`,
		name, email, pwHash,
	).Scan(&user.ID, &user.Name, &user.Email, &user.Role, &createdAt)
	if err != nil {
		var pqErr *pq.Error
		if errors.As(err, &pqErr) && pqErr.Code == "23505" {
			writeError(w, http.StatusConflict, "EMAIL_EXISTS", "email already registered")
			return
		}
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to register user")
		return
	}
	user.CreatedAt = createdAt.UTC().Format(time.RFC3339)

	token, err := s.signJWT(user)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "TOKEN_ERROR", "failed to generate token")
		return
	}

	writeJSON(w, http.StatusCreated, AuthResponse{Token: token, User: user})
}

func (s *Server) handleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}

	var req struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_JSON", "invalid request payload")
		return
	}

	email := strings.ToLower(strings.TrimSpace(req.Email))
	var user UserDTO
	var pwHash string
	var createdAt time.Time

	err := s.db.QueryRowContext(
		r.Context(),
		`SELECT id, name, email, password_hash, role, created_at FROM users WHERE email = $1`,
		email,
	).Scan(&user.ID, &user.Name, &user.Email, &pwHash, &user.Role, &createdAt)
	if err != nil || !verifyPassword(req.Password, pwHash) {
		writeError(w, http.StatusUnauthorized, "INVALID_CREDENTIALS", "invalid email or password")
		return
	}
	user.CreatedAt = createdAt.UTC().Format(time.RFC3339)

	token, err := s.signJWT(user)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "TOKEN_ERROR", "failed to generate token")
		return
	}

	writeJSON(w, http.StatusOK, AuthResponse{Token: token, User: user})
}

func (s *Server) handleMe(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}
	claims, err := s.authenticateRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}

	var user UserDTO
	var createdAt time.Time
	err = s.db.QueryRowContext(
		r.Context(),
		`SELECT id, name, email, role, created_at FROM users WHERE id = $1`,
		claims.Sub,
	).Scan(&user.ID, &user.Name, &user.Email, &user.Role, &createdAt)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "USER_NOT_FOUND", "user not found")
		return
	}
	user.CreatedAt = createdAt.UTC().Format(time.RFC3339)
	writeJSON(w, http.StatusOK, user)
}

func (s *Server) handleProducts(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		s.listProducts(w, r)
	case http.MethodPost:
		s.createProduct(w, r)
	default:
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
	}
}

func (s *Server) listProducts(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	category := strings.TrimSpace(q.Get("category"))
	search := strings.TrimSpace(q.Get("search"))

	page := parseIntOrDefault(q.Get("page"), 1)
	if page < 1 {
		page = 1
	}
	limit := parseIntOrDefault(q.Get("limit"), 20)
	if limit < 1 || limit > 100 {
		limit = 20
	}

	var clauses []string
	var args []any
	argIdx := 1

	if category != "" && !strings.EqualFold(category, "all") {
		clauses = append(clauses, fmt.Sprintf("LOWER(category) = LOWER($%d)", argIdx))
		args = append(args, category)
		argIdx++
	}
	if search != "" {
		clauses = append(clauses, fmt.Sprintf("(name ILIKE '%%' || $%d || '%%' OR description ILIKE '%%' || $%d || '%%')", argIdx, argIdx))
		args = append(args, search)
		argIdx++
	}

	whereSQL := ""
	if len(clauses) > 0 {
		whereSQL = " WHERE " + strings.Join(clauses, " AND ")
	}

	var total int
	if err := s.db.QueryRowContext(r.Context(), "SELECT COUNT(*) FROM products"+whereSQL, args...).Scan(&total); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to count products")
		return
	}

	offset := (page - 1) * limit
	querySQL := fmt.Sprintf(
		"SELECT id, name, description, price::float8, stock, category, created_at FROM products%s ORDER BY id ASC LIMIT $%d OFFSET $%d",
		whereSQL, argIdx, argIdx+1,
	)
	queryArgs := append(append([]any{}, args...), limit, offset)

	rows, err := s.db.QueryContext(r.Context(), querySQL, queryArgs...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to list products")
		return
	}
	defer rows.Close()

	products := make([]ProductDTO, 0)
	for rows.Next() {
		var p ProductDTO
		var createdAt time.Time
		if err := rows.Scan(&p.ID, &p.Name, &p.Description, &p.Price, &p.Stock, &p.Category, &createdAt); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to scan product")
			return
		}
		p.CreatedAt = createdAt.UTC().Format(time.RFC3339)
		products = append(products, p)
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"products": products,
		"data":     products,
		"total":    total,
		"page":     page,
		"limit":    limit,
	})
}

func (s *Server) createProduct(w http.ResponseWriter, r *http.Request) {
	claims, err := s.authenticateRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}
	if claims.Role != "admin" {
		writeError(w, http.StatusForbidden, "FORBIDDEN", "admin privileges required")
		return
	}

	var req struct {
		Name        string  `json:"name"`
		Description string  `json:"description"`
		Price       float64 `json:"price"`
		Stock       int     `json:"stock"`
		Category    string  `json:"category"`
	}
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_JSON", "invalid request payload")
		return
	}
	if strings.TrimSpace(req.Name) == "" || req.Price <= 0 || req.Stock < 0 || strings.TrimSpace(req.Category) == "" {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid product fields")
		return
	}

	var p ProductDTO
	var createdAt time.Time
	err = s.db.QueryRowContext(
		r.Context(),
		`INSERT INTO products (name, description, price, stock, category)
		 VALUES ($1, $2, $3, $4, $5)
		 RETURNING id, name, description, price::float8, stock, category, created_at`,
		strings.TrimSpace(req.Name), req.Description, req.Price, req.Stock, strings.TrimSpace(req.Category),
	).Scan(&p.ID, &p.Name, &p.Description, &p.Price, &p.Stock, &p.Category, &createdAt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to create product")
		return
	}
	p.CreatedAt = createdAt.UTC().Format(time.RFC3339)
	writeJSON(w, http.StatusCreated, p)
}

func (s *Server) handleProductByID(w http.ResponseWriter, r *http.Request) {
	idStr := strings.TrimPrefix(r.URL.Path, "/api/v1/products/")
	id, err := strconv.Atoi(idStr)
	if err != nil || id <= 0 {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid product id")
		return
	}

	switch r.Method {
	case http.MethodGet:
		var p ProductDTO
		var createdAt time.Time
		err := s.db.QueryRowContext(
			r.Context(),
			`SELECT id, name, description, price::float8, stock, category, created_at FROM products WHERE id = $1`,
			id,
		).Scan(&p.ID, &p.Name, &p.Description, &p.Price, &p.Stock, &p.Category, &createdAt)
		if errors.Is(err, sql.ErrNoRows) {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "product not found")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to load product")
			return
		}
		p.CreatedAt = createdAt.UTC().Format(time.RFC3339)
		writeJSON(w, http.StatusOK, p)

	case http.MethodPut:
		claims, authErr := s.authenticateRequest(r)
		if authErr != nil {
			writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", authErr.Error())
			return
		}
		if claims.Role != "admin" {
			writeError(w, http.StatusForbidden, "FORBIDDEN", "admin privileges required")
			return
		}

		var req struct {
			Name        *string  `json:"name"`
			Description *string  `json:"description"`
			Price       *float64 `json:"price"`
			Stock       *int     `json:"stock"`
			Category    *string  `json:"category"`
		}
		if err := decodeJSON(r, &req); err != nil {
			writeError(w, http.StatusBadRequest, "INVALID_JSON", "invalid request payload")
			return
		}
		if req.Price != nil && *req.Price <= 0 {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "price must be > 0")
			return
		}
		if req.Stock != nil && *req.Stock < 0 {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "stock must be >= 0")
			return
		}

		var p ProductDTO
		var createdAt time.Time
		err := s.db.QueryRowContext(
			r.Context(),
			`UPDATE products
			 SET name = COALESCE($1, name),
			     description = COALESCE($2, description),
			     price = COALESCE($3, price),
			     stock = COALESCE($4, stock),
			     category = COALESCE($5, category)
			 WHERE id = $6
			 RETURNING id, name, description, price::float8, stock, category, created_at`,
			req.Name, req.Description, req.Price, req.Stock, req.Category, id,
		).Scan(&p.ID, &p.Name, &p.Description, &p.Price, &p.Stock, &p.Category, &createdAt)
		if errors.Is(err, sql.ErrNoRows) {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "product not found")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to update product")
			return
		}
		p.CreatedAt = createdAt.UTC().Format(time.RFC3339)
		writeJSON(w, http.StatusOK, p)

	case http.MethodDelete:
		claims, authErr := s.authenticateRequest(r)
		if authErr != nil {
			writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", authErr.Error())
			return
		}
		if claims.Role != "admin" {
			writeError(w, http.StatusForbidden, "FORBIDDEN", "admin privileges required")
			return
		}

		res, err := s.db.ExecContext(r.Context(), `DELETE FROM products WHERE id = $1`, id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to delete product")
			return
		}
		affected, _ := res.RowsAffected()
		if affected == 0 {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "product not found")
			return
		}
		writeJSON(w, http.StatusOK, map[string]int{"deleted": id})

	default:
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
	}
}

func (s *Server) handleCart(w http.ResponseWriter, r *http.Request) {
	claims, err := s.authenticateRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}

	switch r.Method {
	case http.MethodGet:
		cart, err := s.loadCart(r.Context(), claims.Sub)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to load cart")
			return
		}
		writeJSON(w, http.StatusOK, cart)
	case http.MethodDelete:
		if _, err := s.db.ExecContext(r.Context(), `DELETE FROM cart_items WHERE user_id = $1`, claims.Sub); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to clear cart")
			return
		}
		writeJSON(w, http.StatusOK, CartResponse{Items: []CartItemDTO{}})
	default:
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
	}
}

func (s *Server) handleCartItems(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}
	claims, err := s.authenticateRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}

	var req struct {
		ProductID int `json:"product_id"`
		Quantity  int `json:"quantity"`
	}
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_JSON", "invalid request payload")
		return
	}
	if req.ProductID <= 0 || req.Quantity <= 0 {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "product_id and quantity > 0 are required")
		return
	}

	var stock int
	err = s.db.QueryRowContext(r.Context(), `SELECT stock FROM products WHERE id = $1`, req.ProductID).Scan(&stock)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "product not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to query product")
		return
	}
	if stock < req.Quantity {
		writeError(w, http.StatusConflict, "INSUFFICIENT_STOCK", "insufficient product stock")
		return
	}

	_, err = s.db.ExecContext(
		r.Context(),
		`INSERT INTO cart_items (user_id, product_id, quantity)
		 VALUES ($1, $2, $3)
		 ON CONFLICT (user_id, product_id)
		 DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity`,
		claims.Sub, req.ProductID, req.Quantity,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to add item to cart")
		return
	}

	cart, err := s.loadCart(r.Context(), claims.Sub)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to load updated cart")
		return
	}
	writeJSON(w, http.StatusOK, cart)
}

func (s *Server) handleCartItemByProductID(w http.ResponseWriter, r *http.Request) {
	claims, err := s.authenticateRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}

	idStr := strings.TrimPrefix(r.URL.Path, "/api/v1/cart/items/")
	productID, err := strconv.Atoi(idStr)
	if err != nil || productID <= 0 {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid product id")
		return
	}

	switch r.Method {
	case http.MethodPut:
		var req struct {
			Quantity int `json:"quantity"`
		}
		if err := decodeJSON(r, &req); err != nil {
			writeError(w, http.StatusBadRequest, "INVALID_JSON", "invalid request payload")
			return
		}
		if req.Quantity < 0 {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "quantity must be >= 0")
			return
		}
		if req.Quantity == 0 {
			_, err = s.db.ExecContext(r.Context(), `DELETE FROM cart_items WHERE user_id = $1 AND product_id = $2`, claims.Sub, productID)
		} else {
			var stock int
			err = s.db.QueryRowContext(r.Context(), `SELECT stock FROM products WHERE id = $1`, productID).Scan(&stock)
			if errors.Is(err, sql.ErrNoRows) {
				writeError(w, http.StatusNotFound, "NOT_FOUND", "product not found")
				return
			}
			if stock < req.Quantity {
				writeError(w, http.StatusConflict, "INSUFFICIENT_STOCK", "insufficient product stock")
				return
			}
			_, err = s.db.ExecContext(
				r.Context(),
				`UPDATE cart_items SET quantity = $1 WHERE user_id = $2 AND product_id = $3`,
				req.Quantity, claims.Sub, productID,
			)
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to update cart item")
			return
		}
		cart, err := s.loadCart(r.Context(), claims.Sub)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to load updated cart")
			return
		}
		writeJSON(w, http.StatusOK, cart)

	case http.MethodDelete:
		if _, err := s.db.ExecContext(r.Context(), `DELETE FROM cart_items WHERE user_id = $1 AND product_id = $2`, claims.Sub, productID); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to delete cart item")
			return
		}
		cart, err := s.loadCart(r.Context(), claims.Sub)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to load updated cart")
			return
		}
		writeJSON(w, http.StatusOK, cart)

	default:
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
	}
}

func (s *Server) loadCart(ctx context.Context, userID int) (CartResponse, error) {
	rows, err := s.db.QueryContext(
		ctx,
		`SELECT p.id, p.name, p.price::float8, ci.quantity, p.stock
		 FROM cart_items ci
		 JOIN products p ON p.id = ci.product_id
		 WHERE ci.user_id = $1
		 ORDER BY p.id ASC`,
		userID,
	)
	if err != nil {
		return CartResponse{}, err
	}
	defer rows.Close()

	items := make([]CartItemDTO, 0)
	var subtotal float64
	var totalItems int
	for rows.Next() {
		var item CartItemDTO
		if err := rows.Scan(&item.ProductID, &item.Name, &item.Price, &item.Quantity, &item.Stock); err != nil {
			return CartResponse{}, err
		}
		item.ProductName = item.Name
		item.Subtotal = roundCents(item.Price * float64(item.Quantity))
		subtotal += item.Subtotal
		totalItems += item.Quantity
		items = append(items, item)
	}

	subtotal = roundCents(subtotal)
	tax := roundCents(subtotal * 0.08)
	total := roundCents(subtotal + tax)

	return CartResponse{
		Items:      items,
		TotalItems: totalItems,
		Subtotal:   subtotal,
		Tax:        tax,
		Total:      total,
	}, nil
}

func (s *Server) handleCheckout(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}

	claims, err := s.authenticateRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}
	idCopy := claims.Sub
	userID := &idCopy

	var req struct {
		ShippingAddress string `json:"shipping_address"`
		PaymentMethod   string `json:"payment_method"`
		IdempotencyKey  string `json:"idempotency_key"`
		Items           []struct {
			ProductID int `json:"product_id"`
			Quantity  int `json:"quantity"`
		} `json:"items"`
	}
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_JSON", "invalid request payload")
		return
	}

	shippingAddress := strings.TrimSpace(req.ShippingAddress)
	if len(shippingAddress) < 5 {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "shipping_address must be at least 5 characters")
		return
	}
	paymentMethod := strings.TrimSpace(req.PaymentMethod)
	if paymentMethod == "" {
		paymentMethod = "credit_card"
	}

	idemKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idemKey == "" {
		idemKey = strings.TrimSpace(req.IdempotencyKey)
	}

	tx, err := s.db.BeginTx(r.Context(), nil)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to start transaction")
		return
	}
	defer func() {
		_ = tx.Rollback()
	}()

	if idemKey != "" {
		if _, err := tx.ExecContext(r.Context(), `SELECT pg_advisory_xact_lock(hashtext($1))`, idemKey); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to acquire idempotency lock")
			return
		}
		existing, found, err := loadOrderByIdempotencyKey(r.Context(), tx, idemKey)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to check idempotency key")
			return
		}
		if found {
			if existing.UserID != nil && *existing.UserID != claims.Sub {
				writeError(w, http.StatusConflict, "IDEMPOTENCY_KEY_CONFLICT", "idempotency key already belongs to another user")
				return
			}
			s.recordCheckoutResult("idempotent_replay")
			writeJSON(w, http.StatusOK, existing)
			return
		}
	}

	type requestedItem struct {
		productID int
		quantity  int
	}
	var lineItems []requestedItem

	if len(req.Items) > 0 {
		merged := make(map[int]int)
		for _, it := range req.Items {
			if it.ProductID <= 0 || it.Quantity <= 0 {
				writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "each item must have positive product_id and quantity")
				return
			}
			merged[it.ProductID] += it.Quantity
		}
		for pid, qty := range merged {
			lineItems = append(lineItems, requestedItem{productID: pid, quantity: qty})
		}
	} else if userID != nil {
		rows, err := tx.QueryContext(
			r.Context(),
			`SELECT product_id, quantity FROM cart_items WHERE user_id = $1 ORDER BY product_id ASC`,
			*userID,
		)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to load cart items")
			return
		}
		for rows.Next() {
			var it requestedItem
			if err := rows.Scan(&it.productID, &it.quantity); err != nil {
				rows.Close()
				writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to scan cart item")
				return
			}
			lineItems = append(lineItems, it)
		}
		rows.Close()
	}

	if len(lineItems) == 0 {
		writeError(w, http.StatusBadRequest, "EMPTY_CART", "no items provided for checkout")
		return
	}

	// Sort by productID to guarantee consistent lock acquisition order under concurrency.
	sort.Slice(lineItems, func(i, j int) bool {
		return lineItems[i].productID < lineItems[j].productID
	})

	var subtotal float64
	var itemsCount int
	orderItems := make([]OrderItemDTO, 0, len(lineItems))

	for _, li := range lineItems {
		var name string
		var price float64
		var stock int
		err := tx.QueryRowContext(
			r.Context(),
			`SELECT name, price::float8, stock FROM products WHERE id = $1 FOR UPDATE`,
			li.productID,
		).Scan(&name, &price, &stock)
		if errors.Is(err, sql.ErrNoRows) {
			writeError(w, http.StatusNotFound, "PRODUCT_NOT_FOUND", fmt.Sprintf("product %d not found", li.productID))
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to lock product inventory")
			return
		}
		if stock < li.quantity {
			s.recordCheckoutResult("insufficient_stock")
			writeError(
				w,
				http.StatusConflict,
				"INSUFFICIENT_STOCK",
				fmt.Sprintf("insufficient stock for %s (requested %d, available %d)", name, li.quantity, stock),
			)
			return
		}

		if _, err := tx.ExecContext(
			r.Context(),
			`UPDATE products SET stock = stock - $1 WHERE id = $2`,
			li.quantity, li.productID,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to update inventory")
			return
		}

		lineTotal := roundCents(price * float64(li.quantity))
		subtotal += lineTotal
		itemsCount += li.quantity
		orderItems = append(orderItems, OrderItemDTO{
			ProductID:   li.productID,
			ProductName: name,
			Quantity:    li.quantity,
			UnitPrice:   price,
			TotalPrice:  lineTotal,
		})
	}

	totalAmount := roundCents(roundCents(subtotal) * 1.08)

	var idemVal any
	if idemKey != "" {
		idemVal = idemKey
	}

	var dbOrderID int
	if err := tx.QueryRowContext(r.Context(), `SELECT nextval('orders_id_seq')`).Scan(&dbOrderID); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to allocate order id")
		return
	}
	orderRef := fmt.Sprintf("ORD-%06d", 100000+dbOrderID)
	var createdAt time.Time

	err = tx.QueryRowContext(
		r.Context(),
		`INSERT INTO orders (id, order_id, user_id, shipping_address, payment_method, status, total_amount, items_count, idempotency_key)
		 VALUES ($1, $2, $3, $4, $5, 'confirmed', $6, $7, $8)
		 RETURNING created_at`,
		dbOrderID, orderRef, userID, shippingAddress, paymentMethod, totalAmount, itemsCount, idemVal,
	).Scan(&createdAt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to insert order")
		return
	}

	for _, oi := range orderItems {
		if _, err := tx.ExecContext(
			r.Context(),
			`INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price, total_price)
			 VALUES ($1, $2, $3, $4, $5, $6)`,
			dbOrderID, oi.ProductID, oi.ProductName, oi.Quantity, oi.UnitPrice, oi.TotalPrice,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to insert order item")
			return
		}
	}

	if userID != nil {
		if _, err := tx.ExecContext(r.Context(), `DELETE FROM cart_items WHERE user_id = $1`, *userID); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to clear user cart")
			return
		}
	}

	if err := tx.Commit(); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to commit checkout transaction")
		return
	}

	s.recordCheckoutResult("confirmed")
	writeJSON(w, http.StatusOK, OrderResponse{
		ID:             dbOrderID,
		OrderID:        orderRef,
		UserID:         userID,
		Status:         "confirmed",
		TotalAmount:    totalAmount,
		ItemsCount:     itemsCount,
		IdempotencyKey: idemKey,
		CreatedAt:      createdAt.UTC().Format(time.RFC3339),
		Items:          orderItems,
	})
}

func loadOrderByIdempotencyKey(ctx context.Context, tx *sql.Tx, key string) (OrderResponse, bool, error) {
	var resp OrderResponse
	var userID sql.NullInt64
	var idemKey sql.NullString
	var createdAt time.Time

	err := tx.QueryRowContext(
		ctx,
		`SELECT id, order_id, user_id, status, total_amount::float8, items_count, idempotency_key, created_at
		 FROM orders WHERE idempotency_key = $1`,
		key,
	).Scan(&resp.ID, &resp.OrderID, &userID, &resp.Status, &resp.TotalAmount, &resp.ItemsCount, &idemKey, &createdAt)
	if errors.Is(err, sql.ErrNoRows) {
		return OrderResponse{}, false, nil
	}
	if err != nil {
		return OrderResponse{}, false, err
	}
	if userID.Valid {
		uid := int(userID.Int64)
		resp.UserID = &uid
	}
	if idemKey.Valid {
		resp.IdempotencyKey = idemKey.String
	}
	resp.CreatedAt = createdAt.UTC().Format(time.RFC3339)

	rows, err := tx.QueryContext(
		ctx,
		`SELECT product_id, product_name, quantity, unit_price::float8, total_price::float8
		 FROM order_items WHERE order_id = $1 ORDER BY id ASC`,
		resp.ID,
	)
	if err != nil {
		return OrderResponse{}, false, err
	}
	defer rows.Close()

	resp.Items = make([]OrderItemDTO, 0)
	for rows.Next() {
		var oi OrderItemDTO
		if err := rows.Scan(&oi.ProductID, &oi.ProductName, &oi.Quantity, &oi.UnitPrice, &oi.TotalPrice); err != nil {
			return OrderResponse{}, false, err
		}
		resp.Items = append(resp.Items, oi)
	}
	return resp, true, nil
}

func (s *Server) handleOrders(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}
	claims, err := s.authenticateRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}

	rows, err := s.db.QueryContext(
		r.Context(),
		`SELECT id, order_id, user_id, status, total_amount::float8, items_count, COALESCE(idempotency_key, ''), created_at
		 FROM orders WHERE user_id = $1 ORDER BY id DESC`,
		claims.Sub,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to load orders")
		return
	}
	defer rows.Close()

	orders := make([]OrderResponse, 0)
	for rows.Next() {
		var o OrderResponse
		var uid int
		var createdAt time.Time
		if err := rows.Scan(&o.ID, &o.OrderID, &uid, &o.Status, &o.TotalAmount, &o.ItemsCount, &o.IdempotencyKey, &createdAt); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to scan order")
			return
		}
		o.UserID = &uid
		o.CreatedAt = createdAt.UTC().Format(time.RFC3339)
		o.Items = []OrderItemDTO{}
		orders = append(orders, o)
	}

	writeJSON(w, http.StatusOK, map[string]any{"orders": orders})
}

func (s *Server) handleOrderByID(w http.ResponseWriter, r *http.Request) {
	claims, err := s.authenticateRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}

	idStr := strings.TrimPrefix(r.URL.Path, "/api/v1/orders/")
	id, err := strconv.Atoi(idStr)
	if err != nil || id <= 0 {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid order id")
		return
	}

	if r.Method == http.MethodDelete {
		var res sql.Result
		if claims.Role == "admin" {
			res, err = s.db.ExecContext(r.Context(), `DELETE FROM orders WHERE id = $1`, id)
		} else {
			res, err = s.db.ExecContext(r.Context(), `DELETE FROM orders WHERE id = $1 AND user_id = $2`, id, claims.Sub)
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to delete order")
			return
		}
		affected, _ := res.RowsAffected()
		if affected == 0 {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "order not found")
			return
		}
		writeJSON(w, http.StatusOK, map[string]int{"deleted": id})
		return
	}

	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}

	var o OrderResponse
	var uid int
	var createdAt time.Time
	err = s.db.QueryRowContext(
		r.Context(),
		`SELECT id, order_id, user_id, status, total_amount::float8, items_count, COALESCE(idempotency_key, ''), created_at
		 FROM orders WHERE id = $1 AND user_id = $2`,
		id, claims.Sub,
	).Scan(&o.ID, &o.OrderID, &uid, &o.Status, &o.TotalAmount, &o.ItemsCount, &o.IdempotencyKey, &createdAt)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "order not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to load order")
		return
	}
	o.UserID = &uid
	o.CreatedAt = createdAt.UTC().Format(time.RFC3339)

	rows, err := s.db.QueryContext(
		r.Context(),
		`SELECT product_id, product_name, quantity, unit_price::float8, total_price::float8
		 FROM order_items WHERE order_id = $1 ORDER BY id ASC`,
		o.ID,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to load order items")
		return
	}
	defer rows.Close()

	o.Items = make([]OrderItemDTO, 0)
	for rows.Next() {
		var oi OrderItemDTO
		if err := rows.Scan(&oi.ProductID, &oi.ProductName, &oi.Quantity, &oi.UnitPrice, &oi.TotalPrice); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to scan order item")
			return
		}
		o.Items = append(o.Items, oi)
	}
	writeJSON(w, http.StatusOK, o)
}

func (s *Server) handleUserByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}
	claims, err := s.authenticateRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", err.Error())
		return
	}
	if claims.Role != "admin" {
		writeError(w, http.StatusForbidden, "FORBIDDEN", "admin privileges required")
		return
	}

	idStr := strings.TrimPrefix(r.URL.Path, "/api/v1/users/")
	id, err := strconv.Atoi(idStr)
	if err != nil || id <= 0 {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid user id")
		return
	}

	tx, err := s.db.BeginTx(r.Context(), nil)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to start transaction")
		return
	}
	defer func() {
		_ = tx.Rollback()
	}()

	var role string
	err = tx.QueryRowContext(r.Context(), `SELECT role FROM users WHERE id = $1`, id).Scan(&role)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "user not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to query user")
		return
	}
	if role == "admin" {
		writeError(w, http.StatusForbidden, "FORBIDDEN", "cannot delete admin account")
		return
	}

	if _, err := tx.ExecContext(r.Context(), `DELETE FROM orders WHERE user_id = $1`, id); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to delete user orders")
		return
	}
	if _, err := tx.ExecContext(r.Context(), `DELETE FROM users WHERE id = $1`, id); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to delete user")
		return
	}
	if err := tx.Commit(); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to commit user deletion")
		return
	}
	writeJSON(w, http.StatusOK, map[string]int{"deleted": id})
}

func (s *Server) signJWT(user UserDTO) (string, error) {
	headerBytes, err := json.Marshal(map[string]string{"alg": "HS256", "typ": "JWT"})
	if err != nil {
		return "", err
	}
	claims := Claims{
		Sub:   user.ID,
		Email: user.Email,
		Name:  user.Name,
		Role:  user.Role,
		Exp:   time.Now().Add(24 * time.Hour).Unix(),
	}
	claimsBytes, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	signingInput := base64.RawURLEncoding.EncodeToString(headerBytes) + "." + base64.RawURLEncoding.EncodeToString(claimsBytes)
	mac := hmac.New(sha256.New, s.jwtSecret)
	mac.Write([]byte(signingInput))
	sig := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	return signingInput + "." + sig, nil
}

func (s *Server) authenticateRequest(r *http.Request) (*Claims, error) {
	authHeader := strings.TrimSpace(r.Header.Get("Authorization"))
	if !strings.HasPrefix(authHeader, "Bearer ") {
		return nil, errors.New("missing bearer token")
	}
	token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return nil, errors.New("invalid token format")
	}
	signingInput := parts[0] + "." + parts[1]
	headerBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return nil, errors.New("invalid token header")
	}
	var header struct {
		Alg string `json:"alg"`
		Typ string `json:"typ"`
	}
	if err := json.Unmarshal(headerBytes, &header); err != nil || header.Alg != "HS256" {
		return nil, errors.New("unsupported token algorithm")
	}

	mac := hmac.New(sha256.New, s.jwtSecret)
	mac.Write([]byte(signingInput))
	expectedSig := mac.Sum(nil)

	actualSig, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil || subtle.ConstantTimeCompare(actualSig, expectedSig) != 1 {
		return nil, errors.New("invalid token signature")
	}

	claimsBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, errors.New("invalid token claims")
	}
	var claims Claims
	if err := json.Unmarshal(claimsBytes, &claims); err != nil {
		return nil, errors.New("malformed token claims")
	}
	if claims.Exp < time.Now().Unix() {
		return nil, errors.New("token expired")
	}
	return &claims, nil
}

const passwordHashIterations = 10000

func derivePasswordKey(password string, salt []byte, iterations int) []byte {
	prf := func(data []byte) []byte {
		m := hmac.New(sha256.New, []byte(password))
		m.Write(data)
		return m.Sum(nil)
	}
	block := append(append([]byte{}, salt...), 0, 0, 0, 1)
	u := prf(block)
	out := append([]byte{}, u...)
	for i := 1; i < iterations; i++ {
		u = prf(u)
		for j := range out {
			out[j] ^= u[j]
		}
	}
	return out
}

func hashPassword(password string) (string, error) {
	salt := make([]byte, 16)
	if _, err := rand.Read(salt); err != nil {
		return "", err
	}
	derived := derivePasswordKey(password, salt, passwordHashIterations)
	return fmt.Sprintf("pbkdf2$%d$%s$%s", passwordHashIterations, hex.EncodeToString(salt), hex.EncodeToString(derived)), nil
}

func verifyPassword(password, stored string) bool {
	parts := strings.Split(stored, "$")
	if len(parts) == 4 && parts[0] == "pbkdf2" {
		iters, err := strconv.Atoi(parts[1])
		if err != nil || iters <= 0 {
			return false
		}
		salt, err := hex.DecodeString(parts[2])
		if err != nil {
			return false
		}
		expectedHash, err := hex.DecodeString(parts[3])
		if err != nil {
			return false
		}
		actualHash := derivePasswordKey(password, salt, iters)
		return subtle.ConstantTimeCompare(actualHash, expectedHash) == 1
	}
	if len(parts) == 2 {
		salt, err := hex.DecodeString(parts[0])
		if err != nil {
			return false
		}
		expectedHash, err := hex.DecodeString(parts[1])
		if err != nil {
			return false
		}
		actualHash := sha256.Sum256(append(salt, []byte(password)...))
		return subtle.ConstantTimeCompare(actualHash[:], expectedHash) == 1
	}
	return false
}

func decodeJSON(r *http.Request, dst any) error {
	dec := json.NewDecoder(http.MaxBytesReader(nil, r.Body, 1<<20))
	return dec.Decode(dst)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, code, msg string) {
	writeJSON(w, status, map[string]any{
		"error":  msg,
		"code":   code,
		"status": status,
	})
}

func roundCents(val float64) float64 {
	return math.Round(val*100) / 100
}

func parseIntOrDefault(raw string, fallback int) int {
	if raw == "" {
		return fallback
	}
	val, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return val
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

func normalizeRouteLabel(path string) string {
	switch {
	case strings.HasPrefix(path, "/api/v1/products/"):
		return "/api/v1/products/{id}"
	case strings.HasPrefix(path, "/api/v1/cart/items/"):
		return "/api/v1/cart/items/{id}"
	case strings.HasPrefix(path, "/api/v1/orders/") && path != "/api/v1/orders/checkout":
		return "/api/v1/orders/{id}"
	default:
		return path
	}
}

func (s *Server) metricsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		durMs := float64(time.Since(start).Microseconds()) / 1000.0
		route := normalizeRouteLabel(r.URL.Path)

		s.metrics.mu.Lock()
		countKey := fmt.Sprintf("%s|%s|%d", r.Method, route, rec.status)
		s.metrics.httpCounts[countKey]++
		durKey := fmt.Sprintf("%s|%s", r.Method, route)
		s.metrics.httpDurationSum[durKey] += durMs
		s.metrics.httpDurationCount[durKey]++
		s.metrics.mu.Unlock()
	})
}

func (s *Server) recordCheckoutResult(result string) {
	s.metrics.mu.Lock()
	s.metrics.checkoutResults[result]++
	s.metrics.mu.Unlock()
}

func (s *Server) handleTelemetryIngest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}

	var req struct {
		RunID   string `json:"run_id"`
		Summary *struct {
			TotalExecutions int64   `json:"total_executions"`
			UniqueTests     int64   `json:"unique_tests"`
			PassRate        float64 `json:"pass_rate"`
			FlakyRate       float64 `json:"flaky_rate"`
			P50Ms           float64 `json:"p50_ms"`
			P95Ms           float64 `json:"p95_ms"`
		} `json:"summary"`
		FailureCategories map[string]int64   `json:"failure_categories"`
		WebVitals         map[string]float64 `json:"web_vitals"`
		Records           []struct {
			RunID           string   `json:"run_id"`
			TestID          string   `json:"test_id"`
			Suite           string   `json:"suite"`
			Status          string   `json:"status"`
			DurationMs      float64  `json:"duration_ms"`
			Browser         string   `json:"browser"`
			Worker          string   `json:"worker"`
			Environment     string   `json:"environment"`
			FailureCategory string   `json:"failure_category"`
			TTFBMs          *float64 `json:"ttfb_ms"`
			FCPMs           *float64 `json:"fcp_ms"`
			LCPMs           *float64 `json:"lcp_ms"`
			CLSScore        *float64 `json:"cls_score"`
			INPMs           *float64 `json:"inp_ms"`
			JSHeapMb        *float64 `json:"js_heap_mb"`
		} `json:"records"`
	}

	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_JSON", "invalid telemetry payload")
		return
	}

	s.metrics.mu.Lock()
	if req.Summary != nil {
		s.metrics.totalExecutions = req.Summary.TotalExecutions
		s.metrics.uniqueTests = req.Summary.UniqueTests
		s.metrics.passRate = req.Summary.PassRate
		s.metrics.flakyRate = req.Summary.FlakyRate
		s.metrics.p50Ms = req.Summary.P50Ms
		s.metrics.p95Ms = req.Summary.P95Ms
	}
	for k, v := range req.WebVitals {
		s.metrics.webVitals[k] = v
	}
	if req.FailureCategories != nil {
		s.metrics.failureCategories = make(map[string]int64, len(req.FailureCategories))
		for k, v := range req.FailureCategories {
			s.metrics.failureCategories[k] = v
		}
	}
	s.metrics.mu.Unlock()

	for _, rec := range req.Records {
		runID := rec.RunID
		if runID == "" {
			runID = req.RunID
		}
		if runID == "" || rec.TestID == "" {
			continue
		}
		suite := rec.Suite
		if suite == "" {
			suite = "all"
		}
		browser := rec.Browser
		if browser == "" {
			browser = "chromium"
		}
		worker := rec.Worker
		if worker == "" {
			worker = "main"
		}
		env := rec.Environment
		if env == "" {
			env = "local"
		}
		if _, err := s.db.ExecContext(
			r.Context(),
			`INSERT INTO test_execution_telemetry
			 (run_id, test_id, suite, status, duration_ms, browser, worker, environment, failure_category,
			  ttfb_ms, fcp_ms, lcp_ms, cls_score, inp_ms, js_heap_mb)
			 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
			 ON CONFLICT (run_id, test_id, worker) DO UPDATE
			 SET status = EXCLUDED.status,
			     duration_ms = EXCLUDED.duration_ms,
			     failure_category = EXCLUDED.failure_category`,
			runID, rec.TestID, suite, rec.Status, rec.DurationMs, browser, worker, env, rec.FailureCategory,
			rec.TTFBMs, rec.FCPMs, rec.LCPMs, rec.CLSScore, rec.INPMs, rec.JSHeapMb,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to persist telemetry record")
			return
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"ingested_records": len(req.Records),
		"status":           "ok",
	})
}

func promEscape(val string) string {
	val = strings.ReplaceAll(val, `\`, `\\`)
	val = strings.ReplaceAll(val, `"`, `\"`)
	val = strings.ReplaceAll(val, "\n", `\n`)
	return val
}

func (s *Server) handleMetrics(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method not allowed")
		return
	}

	var b strings.Builder

	s.metrics.mu.RLock()
	b.WriteString("# HELP aegis_http_requests_total Total HTTP requests processed by Go SUT backend\n")
	b.WriteString("# TYPE aegis_http_requests_total counter\n")
	httpKeys := make([]string, 0, len(s.metrics.httpCounts))
	for k := range s.metrics.httpCounts {
		httpKeys = append(httpKeys, k)
	}
	sort.Strings(httpKeys)
	for _, k := range httpKeys {
		parts := strings.SplitN(k, "|", 3)
		if len(parts) == 3 {
			fmt.Fprintf(&b, "aegis_http_requests_total{method=%q,route=%q,status=%q} %d\n",
				parts[0], parts[1], parts[2], s.metrics.httpCounts[k])
		}
	}

	b.WriteString("# HELP aegis_http_request_duration_ms_sum Total HTTP request duration in ms\n")
	b.WriteString("# TYPE aegis_http_request_duration_ms_sum counter\n")
	b.WriteString("# HELP aegis_http_request_duration_ms_count Total HTTP request latency samples\n")
	b.WriteString("# TYPE aegis_http_request_duration_ms_count counter\n")
	durKeys := make([]string, 0, len(s.metrics.httpDurationCount))
	for k := range s.metrics.httpDurationCount {
		durKeys = append(durKeys, k)
	}
	sort.Strings(durKeys)
	for _, k := range durKeys {
		parts := strings.SplitN(k, "|", 2)
		if len(parts) == 2 {
			fmt.Fprintf(&b, "aegis_http_request_duration_ms_sum{method=%q,route=%q} %.3f\n",
				parts[0], parts[1], s.metrics.httpDurationSum[k])
			fmt.Fprintf(&b, "aegis_http_request_duration_ms_count{method=%q,route=%q} %d\n",
				parts[0], parts[1], s.metrics.httpDurationCount[k])
		}
	}

	b.WriteString("# HELP aegis_orders_checkout_total ACID checkout outcomes\n")
	b.WriteString("# TYPE aegis_orders_checkout_total counter\n")
	for _, result := range []string{"confirmed", "idempotent_replay", "insufficient_stock"} {
		fmt.Fprintf(&b, "aegis_orders_checkout_total{result=%q} %d\n", result, s.metrics.checkoutResults[result])
	}

	b.WriteString("# HELP aegis_test_executions_total Total recorded test executions in current history\n")
	b.WriteString("# TYPE aegis_test_executions_total gauge\n")
	fmt.Fprintf(&b, "aegis_test_executions_total %d\n", s.metrics.totalExecutions)

	b.WriteString("# HELP aegis_test_unique_count Unique test node IDs recorded\n")
	b.WriteString("# TYPE aegis_test_unique_count gauge\n")
	fmt.Fprintf(&b, "aegis_test_unique_count %d\n", s.metrics.uniqueTests)

	b.WriteString("# HELP aegis_test_pass_rate_percent Overall test suite pass rate percentage\n")
	b.WriteString("# TYPE aegis_test_pass_rate_percent gauge\n")
	fmt.Fprintf(&b, "aegis_test_pass_rate_percent %.2f\n", s.metrics.passRate)

	b.WriteString("# HELP aegis_test_flaky_rate_percent Comparable-condition flaky test ratio percentage\n")
	b.WriteString("# TYPE aegis_test_flaky_rate_percent gauge\n")
	fmt.Fprintf(&b, "aegis_test_flaky_rate_percent %.2f\n", s.metrics.flakyRate)

	b.WriteString("# HELP aegis_test_duration_p50_ms Suite median test duration in ms\n")
	b.WriteString("# TYPE aegis_test_duration_p50_ms gauge\n")
	fmt.Fprintf(&b, "aegis_test_duration_p50_ms %.2f\n", s.metrics.p50Ms)

	b.WriteString("# HELP aegis_test_duration_p95_ms Suite 95th percentile test duration in ms\n")
	b.WriteString("# TYPE aegis_test_duration_p95_ms gauge\n")
	fmt.Fprintf(&b, "aegis_test_duration_p95_ms %.2f\n", s.metrics.p95Ms)

	b.WriteString("# HELP aegis_web_vitals_gauge Latest captured Core Web Vitals and CDP metrics\n")
	b.WriteString("# TYPE aegis_web_vitals_gauge gauge\n")
	vitalKeys := make([]string, 0, len(s.metrics.webVitals))
	for k := range s.metrics.webVitals {
		vitalKeys = append(vitalKeys, k)
	}
	sort.Strings(vitalKeys)
	for _, k := range vitalKeys {
		fmt.Fprintf(&b, "aegis_web_vitals_gauge{metric=\"%s\"} %.4f\n", promEscape(k), s.metrics.webVitals[k])
	}

	b.WriteString("# HELP aegis_failures_by_category_total Failure counts grouped by AI classification category\n")
	b.WriteString("# TYPE aegis_failures_by_category_total gauge\n")
	for k, v := range s.metrics.failureCategories {
		fmt.Fprintf(&b, "aegis_failures_by_category_total{category=\"%s\"} %d\n", promEscape(k), v)
	}
	s.metrics.mu.RUnlock()

	// Live product inventory stock gauges from PostgreSQL
	b.WriteString("# HELP aegis_inventory_stock_units Live product inventory units in PostgreSQL\n")
	b.WriteString("# TYPE aegis_inventory_stock_units gauge\n")
	rows, err := s.db.QueryContext(r.Context(), `SELECT id, name, category, stock FROM products ORDER BY id ASC LIMIT 50`)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var id, stock int
			var name, cat string
			if scanErr := rows.Scan(&id, &name, &cat, &stock); scanErr == nil {
				fmt.Fprintf(&b, "aegis_inventory_stock_units{product_id=\"%d\",product_name=\"%s\",category=\"%s\"} %d\n",
					id, promEscape(name), promEscape(cat), stock)
			}
		}
	}

	w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(b.String()))
}
