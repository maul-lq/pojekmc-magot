-- Data dummy untuk Smart Maggot Farming Monitor.
--
-- Prasyarat:
--   1. Database db_mocom_maggot dan tabel aplikasi sudah dibuat.
--   2. Jalankan pada database testing/development, bukan production.
--
-- Konfigurasi ada pada CALL di bagian bawah file:
--   CALL seed_dummy_sensor_data(jumlah_hari, interval_menit);
--
-- Konfigurasi default menghasilkan:
--   - 7 hari data
--   - 1 pembacaan setiap 30 menit
--   - 336 pembacaan sensor
--   - campuran kondisi normal, suhu/gas abnormal, masalah DHT22,
--     buzzer tidak konsisten, dan notifikasi transisi
--
-- Script ini MENAMBAHKAN data. Jalankan perintah berikut secara manual hanya
-- jika ingin mengosongkan seluruh data sensor pada database disposable:
--   DELETE FROM notifications;
--   DELETE FROM sensor_readings;

USE db_mocom_maggot;
SET time_zone = '+00:00';

DROP PROCEDURE IF EXISTS seed_dummy_sensor_data;

DELIMITER //

CREATE PROCEDURE seed_dummy_sensor_data(
    IN p_days INT,
    IN p_interval_minutes INT
)
BEGIN
    DECLARE v_i INT DEFAULT 0;
    DECLARE v_total INT;
    DECLARE v_reading_id BIGINT UNSIGNED;
    DECLARE v_received_at DATETIME(6);
    DECLARE v_temperature DECIMAL(6,2);
    DECLARE v_humidity DECIMAL(6,2);
    DECLARE v_gas INT UNSIGNED;
    DECLARE v_buzzer VARCHAR(3);
    DECLARE v_expected_buzzer VARCHAR(3);
    DECLARE v_temperature_abnormal BOOLEAN;
    DECLARE v_gas_abnormal BOOLEAN;
    DECLARE v_has_problem BOOLEAN;
    DECLARE v_buzzer_inconsistent BOOLEAN;
    DECLARE v_previous_temperature_abnormal BOOLEAN DEFAULT FALSE;
    DECLARE v_previous_gas_abnormal BOOLEAN DEFAULT FALSE;
    DECLARE v_previous_has_problem BOOLEAN DEFAULT FALSE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_days < 1 OR p_days > 30 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Jumlah hari harus berada pada rentang 1 sampai 30.';
    END IF;

    IF p_interval_minutes < 1 OR p_interval_minutes > 1440 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Interval menit harus berada pada rentang 1 sampai 1440.';
    END IF;

    SET v_total = FLOOR(p_days * 24 * 60 / p_interval_minutes);

    START TRANSACTION;

    WHILE v_i < v_total DO
        SET v_received_at = DATE_SUB(
            UTC_TIMESTAMP(6),
            INTERVAL ((v_total - 1 - v_i) * p_interval_minutes) MINUTE
        );

        -- Masalah pembacaan DHT22 muncul sesekali.
        SET v_has_problem = MOD(v_i, 97) = 0;

        IF v_has_problem THEN
            SET v_temperature = 0.00;
            SET v_humidity = 0.00;
        ELSE
            -- Mayoritas suhu normal, dengan beberapa rangkaian suhu tinggi/rendah.
            SET v_temperature = 31.00 + (MOD(v_i, 45) / 10);
            IF MOD(v_i, 53) IN (0, 1, 2) THEN
                SET v_temperature = 40.00 + (MOD(v_i, 10) / 10);
            ELSEIF MOD(v_i, 71) IN (0, 1) THEN
                SET v_temperature = 27.00 + (MOD(v_i, 10) / 10);
            END IF;

            SET v_humidity = 60.00 + MOD(v_i * 7, 26);
        END IF;

        -- Gas melewati ambang 2.000 pada beberapa rangkaian pembacaan.
        SET v_gas = 1050 + MOD(v_i * 37, 850);
        IF MOD(v_i, 67) IN (0, 1, 2, 3) THEN
            SET v_gas = 2200 + MOD(v_i * 29, 700);
        END IF;

        SET v_temperature_abnormal = IF(
            v_has_problem,
            FALSE,
            NOT (v_temperature > 29 AND v_temperature < 39)
        );
        SET v_gas_abnormal = v_gas > 2000;
        SET v_expected_buzzer = IF(
            v_temperature_abnormal OR v_gas_abnormal,
            'ON',
            'OFF'
        );

        -- Beberapa pembacaan sengaja memiliki status buzzer yang salah.
        SET v_buzzer_inconsistent = NOT v_has_problem AND MOD(v_i, 83) = 10;
        SET v_buzzer = IF(
            v_buzzer_inconsistent,
            IF(v_expected_buzzer = 'ON', 'OFF', 'ON'),
            v_expected_buzzer
        );

        INSERT INTO sensor_readings (
            temperature,
            humidity,
            gas,
            buzzer,
            temperature_abnormal,
            gas_abnormal,
            has_problem,
            buzzer_inconsistent,
            received_at
        ) VALUES (
            v_temperature,
            v_humidity,
            v_gas,
            v_buzzer,
            v_temperature_abnormal,
            v_gas_abnormal,
            v_has_problem,
            v_buzzer_inconsistent,
            v_received_at
        );

        SET v_reading_id = LAST_INSERT_ID();

        -- Sama seperti backend: notifikasi hanya dibuat ketika kondisi mulai aktif.
        IF v_temperature_abnormal AND NOT v_previous_temperature_abnormal THEN
            INSERT INTO notifications (
                sensor_reading_id,
                notification_type,
                severity,
                message,
                created_at
            ) VALUES (
                v_reading_id,
                'temperature',
                'danger',
                CONCAT(
                    'Suhu abnormal terdeteksi: ',
                    FORMAT(v_temperature, 1),
                    ' °C.'
                ),
                v_received_at
            );
        END IF;

        IF v_gas_abnormal AND NOT v_previous_gas_abnormal THEN
            INSERT INTO notifications (
                sensor_reading_id,
                notification_type,
                severity,
                message,
                created_at
            ) VALUES (
                v_reading_id,
                'gas',
                'danger',
                CONCAT('Nilai gas melewati ambang: ', v_gas, '.'),
                v_received_at
            );
        END IF;

        IF v_has_problem AND NOT v_previous_has_problem THEN
            INSERT INTO notifications (
                sensor_reading_id,
                notification_type,
                severity,
                message,
                created_at
            ) VALUES (
                v_reading_id,
                'data_problem',
                'warning',
                'Pembacaan DHT22 bermasalah atau gagal.',
                v_received_at
            );
        END IF;

        SET v_previous_temperature_abnormal = v_temperature_abnormal;
        SET v_previous_gas_abnormal = v_gas_abnormal;
        SET v_previous_has_problem = v_has_problem;
        SET v_i = v_i + 1;
    END WHILE;

    COMMIT;

    SELECT
        v_total AS inserted_readings,
        (
            SELECT COUNT(*)
            FROM sensor_readings
            WHERE received_at >= DATE_SUB(
                UTC_TIMESTAMP(6),
                INTERVAL p_days DAY
            )
        ) AS total_recent_readings;
END//

DELIMITER ;

CALL seed_dummy_sensor_data(7, 30);
DROP PROCEDURE seed_dummy_sensor_data;
