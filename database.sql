-- Vapes Shop Database Schema
-- This file creates the necessary tables for the vape shop website

-- Create database
CREATE DATABASE IF NOT EXISTS vapes_shop CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE vapes_shop;

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    category ENUM('vapes', 'liquidos', 'accesorios') NOT NULL,
    image VARCHAR(255),
    stock INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_category (category),
    INDEX idx_price (price)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_name VARCHAR(255),
    customer_email VARCHAR(255),
    customer_phone VARCHAR(50),
    total_amount DECIMAL(10, 2) NOT NULL,
    status ENUM('pending', 'processing', 'completed', 'cancelled') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Order items table
CREATE TABLE IF NOT EXISTS order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    quantity INT NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    subtotal DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT,
    INDEX idx_order_id (order_id),
    INDEX idx_product_id (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert sample products
INSERT INTO products (name, description, price, category, image, stock) VALUES
('Vape Pod Premium', 'Dispositivo compacto y elegante con batería de larga duración', 29.99, 'vapes', '🔋', 50),
('Vape Mod Avanzado', 'Mod avanzado con control de temperatura y potencia', 79.99, 'vapes', '⚡', 30),
('Líquido Frutas Tropicales', 'Sabor a frutas tropicales, 60ml, 3mg nicotina', 14.99, 'liquidos', '🍹', 100),
('Líquido Menta Fresca', 'Sabor a menta refrescante, 60ml, 6mg nicotina', 14.99, 'liquidos', '🌿', 100),
('Líquido Café Premium', 'Sabor a café expreso, 60ml, 0mg nicotina', 16.99, 'liquidos', '☕', 80),
('Coils de Repuesto', 'Pack de 5 coils compatibles, resistencia 0.5ohm', 9.99, 'accesorios', '🔧', 150),
('Cargador USB-C', 'Cargador rápido USB-C para dispositivos vape', 7.99, 'accesorios', '🔌', 200),
('Estuche Protector', 'Estuche de transporte con compartimentos', 12.99, 'accesorios', '💼', 75),
('Vape Desechable Mix', 'Vape desechable con múltiples sabores, 2000 puffs', 8.99, 'vapes', '🌈', 120),
('Kit Inicial Completo', 'Kit completo para principiantes con todo lo necesario', 49.99, 'vapes', '📦', 40);
