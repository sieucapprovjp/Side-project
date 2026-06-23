import json

# 1. SYSTEM PROMPT: Nén cấu trúc CSDL và cấp quyền DBA cho mô hình
SYSTEM_PROMPT = """Bạn là chuyên gia PostgreSQL DBA cho Hệ thống Quản lý Bệnh viện.
Nhiệm vụ của bạn:
1. Dịch ngôn ngữ tự nhiên sang câu lệnh SQL (SELECT, INSERT, UPDATE, DELETE).
2. Sinh mã tạo các cấu trúc cơ sở dữ liệu nâng cao (CREATE VIEW, FUNCTION, PROCEDURE, TRIGGER, INDEX) theo đúng chuẩn PostgreSQL plpgsql.

Schema rút gọn:
- visitor(visitor_id, full_name, gender, date_of_birth, phone)
- patient(patient_id, visitor_id, health_insurance_no)
- departments(department_id, department_name)
- doctors(doctor_id, full_name, specialization, department_id)
- rooms(room_id, room_number, room_type, capacity, price_per_day, department_id)
- appointments(appointment_id, visitor_id, doctor_id, appointment_time, reason, status)
- medical_records(record_id, visitor_id, doctor_id, appointment_id, diagnosis, symptoms, treatment_plan)
- admissions(admission_id, patient_id, room_id, admission_date, discharge_date, status)
- medicines(medicine_id, medicine_name, price, stock_quantity)
- prescriptions(prescription_id, record_id, medicine_id, dosage, quantity)
- invoices(invoice_id, visitor_id, record_id, total_amount, payment_status)
- invoice_details, invoice_prescriptions, invoice_rooms, invoice_lab_tests

Views hỗ trợ:
- view_admin_overview (tổng quan hệ thống)
- view_admin_rooms (tình trạng phòng)
- view_admin_medicine_stock (kho thuốc)
- view_admin_revenue (doanh thu)

Procedures & Functions:
- sp_discharge_patient(p_admission_id, p_discharge_reason)
- sp_pay_invoice(p_invoice_id)
- fn_patient_spending(p_visitor_id)
- fn_department_revenue(p_dept_id)"""

# 2. DATASET: Tổng hợp toàn bộ nghiệp vụ (Query + DBA)
raw_data = [
    # --- QUERY CƠ BẢN & THỐNG KÊ ---
    ("Hiển thị danh sách bác sĩ, số bệnh nhân họ đã khám và số lịch hẹn đã hoàn thành.",
     "SELECT d.doctor_id, d.full_name AS doctor_name, d.specialization, COUNT(DISTINCT mr.visitor_id) AS total_patients, COUNT(DISTINCT a.appointment_id) FILTER (WHERE a.status = 'Completed') AS completed_appointments FROM doctors d LEFT JOIN medical_records mr ON d.doctor_id = mr.doctor_id LEFT JOIN appointments a ON d.doctor_id = a.doctor_id GROUP BY d.doctor_id, d.full_name, d.specialization ORDER BY total_patients DESC;"),

    ("Tính tổng doanh thu và số lượng hóa đơn của từng khoa.",
     "SELECT dep.department_id, dep.department_name, COALESCE(SUM(i.total_amount), 0) AS total_revenue, COUNT(DISTINCT i.invoice_id) AS total_invoices FROM departments dep LEFT JOIN doctors d ON dep.department_id = d.department_id LEFT JOIN medical_records mr ON d.doctor_id = mr.doctor_id LEFT JOIN invoices i ON mr.record_id = i.record_id GROUP BY dep.department_id, dep.department_name ORDER BY total_revenue DESC;"),

    ("Tìm top 3 bệnh nhân mua thuốc hết nhiều tiền nhất.",
     "SELECT v.visitor_id, v.full_name, SUM(ip.amount) AS total_medicine_cost FROM visitor v JOIN invoices i ON v.visitor_id = i.visitor_id JOIN invoice_prescriptions ip ON i.invoice_id = ip.invoice_id GROUP BY v.visitor_id, v.full_name ORDER BY total_medicine_cost DESC LIMIT 3;"),

    ("Có phòng bệnh nào chưa từng có bệnh nhân nằm không?",
     "SELECT r.room_id, r.room_number, r.room_type, r.capacity, r.price_per_day FROM rooms r LEFT JOIN admissions a ON r.room_id = a.room_id WHERE a.admission_id IS NULL ORDER BY r.room_number;"),

    ("Liệt kê những người có lịch hẹn nhưng chưa có hồ sơ bệnh án.",
     "SELECT v.visitor_id, v.full_name, v.phone, COUNT(a.appointment_id) AS total_appointments FROM visitor v JOIN appointments a ON v.visitor_id = a.visitor_id LEFT JOIN medical_records mr ON v.visitor_id = mr.visitor_id WHERE mr.record_id IS NULL GROUP BY v.visitor_id, v.full_name, v.phone ORDER BY v.full_name;"),

    ("Loại thuốc nào được kê nhiều nhất và bác sĩ nào hay kê loại đó nhất?",
     "SELECT medicine_name, doctor_name, total_prescribed, prescription_count FROM (SELECT m.medicine_name, d.full_name AS doctor_name, SUM(p.quantity) AS total_prescribed, COUNT(p.prescription_id) AS prescription_count, ROW_NUMBER() OVER (PARTITION BY m.medicine_id ORDER BY SUM(p.quantity) DESC) AS rn FROM medicines m JOIN prescriptions p ON m.medicine_id = p.medicine_id JOIN medical_records mr ON p.record_id = mr.record_id JOIN doctors d ON mr.doctor_id = d.doctor_id GROUP BY m.medicine_id, m.medicine_name, d.doctor_id, d.full_name) ranked WHERE rn = 1 ORDER BY total_prescribed DESC;"),

    ("Ai là bệnh nhân nhập viện lâu nhất mà chưa xuất viện?",
     "SELECT v.full_name AS patient_name, ad.admission_date, CURRENT_DATE - ad.admission_date AS days_hospitalized, r.room_number, dep.department_name FROM admissions ad JOIN patient p ON ad.patient_id = p.patient_id JOIN visitor v ON p.visitor_id = v.visitor_id JOIN rooms r ON ad.room_id = r.room_id JOIN departments dep ON r.department_id = dep.department_id WHERE ad.status = 'Admitted' ORDER BY days_hospitalized DESC;"),

    ("Lấy danh sách các hóa đơn có tổng tiền lớn hơn mức trung bình của toàn bệnh viện.",
     "SELECT i.invoice_id, v.full_name AS visitor_name, i.total_amount, (SELECT AVG(total_amount) FROM invoices) AS avg_amount FROM invoices i JOIN visitor v ON i.visitor_id = v.visitor_id WHERE i.total_amount > (SELECT AVG(total_amount) FROM invoices) ORDER BY i.total_amount DESC;"),

    ("Lấy danh sách những người có lịch hẹn nhưng chưa từng làm xét nghiệm nào.",
     "SELECT v.visitor_id, v.full_name, v.phone, COUNT(a.appointment_id) AS total_appointments FROM visitor v JOIN appointments a ON v.visitor_id = a.visitor_id WHERE NOT EXISTS (SELECT 1 FROM medical_records mr JOIN lab_orders lo ON mr.record_id = lo.record_id WHERE mr.visitor_id = v.visitor_id) GROUP BY v.visitor_id, v.full_name, v.phone ORDER BY v.full_name;"),

    ("Xem danh sách các hóa đơn chưa thanh toán.",
     "SELECT v.full_name AS visitor_name, i.invoice_id, i.total_amount, i.payment_status, i.created_at FROM invoices i JOIN visitor v ON i.visitor_id = v.visitor_id WHERE i.payment_status = 'Unpaid' ORDER BY i.created_at DESC;"),

    # --- SỬ DỤNG VIEWS ---
    ("Cho tôi xem báo cáo tổng quan tình hình bệnh viện hiện tại.",
     "SELECT * FROM view_admin_overview;"),

    ("Xem danh sách nhân viên và bác sĩ của bệnh viện.",
     "SELECT * FROM view_admin_staff;"),

    ("Kiểm tra số lượng thuốc còn tồn trong kho.",
     "SELECT * FROM view_admin_medicine_stock;"),

    ("Kiểm tra tình trạng trống của các phòng bệnh lúc này.",
     "SELECT * FROM view_admin_rooms;"),

    ("Cho tôi xem thống kê doanh thu của bệnh viện.",
     "SELECT * FROM view_admin_revenue;"),

    # --- SỬ DỤNG STORED PROCEDURES & FUNCTIONS ---
    ("Làm thủ tục xuất viện cho bệnh nhân ở ca nhập viện số 5, lý do là đã hồi phục hoàn toàn.",
     "CALL sp_discharge_patient(5, 'Đã hồi phục hoàn toàn');"),

    ("Thực hiện thanh toán cho hóa đơn mã số 12.",
     "CALL sp_pay_invoice(12);"),

    ("Tính tổng số tiền mà khách hàng có ID 1 đã chi tiêu tại bệnh viện.",
     "SELECT fn_patient_spending(1) AS total_spent;"),

    ("Xem tổng doanh thu của khoa tim mạch (ID là 1).",
     "SELECT fn_department_revenue(1) AS dept_revenue;"),

    ("Kiểm tra tổng doanh thu các hóa đơn đã thanh toán thành công của toàn hệ thống.",
     "SELECT get_total_revenue() AS total_revenue;"),

    # --- DBA: YÊU CẦU TẠO VIEW ---
    ("Tạo một view tên là view_admin_revenue để ban giám đốc xem tổng quan doanh thu từ hóa đơn của từng bệnh nhân.",
     "CREATE VIEW view_admin_revenue AS SELECT i.invoice_id, v.full_name AS visitor_name, i.total_amount, i.payment_status, i.created_at FROM invoices i JOIN visitor v ON i.visitor_id = v.visitor_id;"),

    ("Viết lệnh tạo view xem tình trạng giường trống của các phòng bệnh.",
     "CREATE VIEW view_admin_rooms AS SELECT r.room_id, r.room_number, r.room_type, r.capacity, COUNT(a.admission_id) AS current_patients, r.capacity - COUNT(a.admission_id) AS available_beds, r.price_per_day, dep.department_name FROM rooms r JOIN departments dep ON r.department_id = dep.department_id LEFT JOIN admissions a ON r.room_id = a.room_id AND a.status = 'Admitted' GROUP BY r.room_id, r.room_number, r.room_type, r.capacity, r.price_per_day, dep.department_name;"),

    # --- DBA: YÊU CẦU TẠO TRIGGER & FUNCTION ---
    ("Viết một trigger tự động trừ số lượng thuốc trong kho (bảng medicines) mỗi khi có đơn thuốc mới được kê (bảng prescriptions). Nếu không đủ thuốc thì báo lỗi.",
     "CREATE OR REPLACE FUNCTION check_stock() RETURNS TRIGGER AS $$\nBEGIN\n    IF (SELECT stock_quantity FROM medicines WHERE medicine_id = NEW.medicine_id) < NEW.quantity THEN\n        RAISE EXCEPTION 'Not enough stock';\n    END IF;\n    UPDATE medicines SET stock_quantity = stock_quantity - NEW.quantity WHERE medicine_id = NEW.medicine_id;\n    RETURN NEW;\nEND;\n$$ LANGUAGE plpgsql;\n\nCREATE TRIGGER trg_stock BEFORE INSERT ON prescriptions FOR EACH ROW EXECUTE FUNCTION check_stock();"),

    ("Làm sao để tổng tiền của hóa đơn (invoices) tự động cập nhật mỗi khi thêm, sửa, xóa một chi tiết hóa đơn (invoice_details)? Viết trigger cho việc này.",
     "CREATE OR REPLACE FUNCTION update_total() RETURNS TRIGGER AS $$\nDECLARE\n    target_invoice_id INT;\nBEGIN\n    IF TG_OP = 'DELETE' THEN\n        target_invoice_id = OLD.invoice_id;\n    ELSE\n        target_invoice_id = NEW.invoice_id;\n    END IF;\n    UPDATE invoices SET total_amount = COALESCE((SELECT SUM(amount) FROM invoice_details WHERE invoice_id = target_invoice_id), 0) WHERE invoice_id = target_invoice_id;\n    IF TG_OP = 'DELETE' THEN\n        RETURN OLD;\n    END IF;\n    RETURN NEW;\nEND;\n$$ LANGUAGE plpgsql;\n\nCREATE TRIGGER trg_total AFTER INSERT OR UPDATE OR DELETE ON invoice_details FOR EACH ROW EXECUTE FUNCTION update_total();"),

    # --- DBA: YÊU CẦU TẠO PROCEDURE ---
    ("Tạo procedure tên sp_pay_invoice nhận vào ID hóa đơn để chuyển trạng thái thanh toán thành 'Paid'. Nếu không tìm thấy thì báo lỗi.",
     "CREATE OR REPLACE PROCEDURE sp_pay_invoice(p_invoice_id INT) LANGUAGE plpgsql AS $$\nBEGIN\n    UPDATE invoices SET payment_status = 'Paid' WHERE invoice_id = p_invoice_id AND payment_status = 'Unpaid';\n    IF NOT FOUND THEN\n        RAISE EXCEPTION 'Invoice ID % not found or already paid', p_invoice_id;\n    END IF;\nEND;\n$$;"),

    # --- DBA: YÊU CẦU TỐI ƯU HÓA (INDEX & EXPLAIN) ---
    ("Đánh index để tăng tốc độ tìm kiếm lịch hẹn của bác sĩ theo thời gian, sau đó dùng lệnh EXPLAIN ANALYZE để đo thời gian chạy truy vấn tìm lịch từ tháng 5 đến tháng 6 năm 2026 của bác sĩ số 1.",
     "CREATE INDEX IF NOT EXISTS idx_appointments_doctor_time ON appointments(doctor_id, appointment_time);\n\nEXPLAIN ANALYZE SELECT a.appointment_id, a.appointment_time, v.full_name AS patient_name, a.reason, a.status FROM appointments a JOIN visitor v ON a.visitor_id = v.visitor_id WHERE a.doctor_id = 1 AND a.appointment_time BETWEEN '2026-05-01' AND '2026-06-30' ORDER BY a.appointment_time;")
]

# 3. AUGMENTATION: Nhân bản và làm phong phú câu hỏi
augmented_data = []
for user_query, sql_query in raw_data:
    # 1. Dạng chuẩn/trực tiếp
    augmented_data.append({
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
            {"role": "assistant", "content": sql_query}
        ]
    })

    # 2. Dạng ngắn gọn (mô phỏng thao tác nhanh trên clipboard)
    short_query = user_query.replace("Hiển thị ", "").replace("Lấy danh sách ", "").replace("Cho tôi xem ",
                                                                                            "Xem ").replace(
        "Viết lệnh ", "").replace("Làm sao để ", "")
    augmented_data.append({
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": short_query},
            {"role": "assistant", "content": sql_query}
        ]
    })

# 4. XUẤT FILE JSON ĐỂ FINETUNE
output_filename = "hospital_finetune_dataset.json"
with open(output_filename, "w", encoding="utf-8") as f:
    json.dump(augmented_data, f, ensure_ascii=False, indent=2)

print(f"Đã tạo thành công dataset '{output_filename}' với {len(augmented_data)} mẫu hội thoại!")