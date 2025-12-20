from flask import render_template, current_app
from werkzeug.utils import secure_filename
import os, uuid, cv2, imageio
from ultralytics import YOLO

# Карта для русских названий
CLASS_RU = {
    'person': 'Human',
    'car':    'Car'
}

# Кэш моделей
YOLO_CACHE = {}


def load_model(model_filename):
    path = os.path.join(current_app.config['YOLO_MODELS_DIR'], model_filename)
    if model_filename not in YOLO_CACHE:
        YOLO_CACHE[model_filename] = YOLO(path)
    return YOLO_CACHE[model_filename]


def detect_and_process(request):
    # 1) Сохранение входного файла
    file       = request.files['file']
    model_name = request.form['model']
    ext        = secure_filename(file.filename).rsplit('.', 1)[-1].lower()
    uid        = uuid.uuid4().hex

    upload_dir = current_app.config['UPLOAD_FOLDER']
    src_path   = os.path.join(upload_dir, f"src_{uid}.{ext}")
    file.save(src_path)

    # 2) Подготовка пути для результата
    res_ext  = 'mp4' if ext in ('mp4','avi','mov') else ext
    res_path = os.path.join(upload_dir, f"res_{uid}.{res_ext}")

    # 3) Загрузка модели
    yolo = load_model(model_name)

    # Для GIF/видео: хранение уникальных ID
    id_map     = {}
    next_label = 1

    # 4) Ветка: статика (JPEG/PNG)
    if ext in ('jpg','jpeg','png'):
        img    = cv2.imread(src_path)
        result = yolo(img)[0]
        counts = {'person':0, 'car':0}

        for box in result.boxes:
            cls       = int(box.cls.cpu().numpy())
            name_en   = yolo.names[cls]                     # 'person' или 'car'
            name_ru   = CLASS_RU.get(name_en, name_en)      # русская подпись
            x1,y1,x2,y2 = map(int, box.xyxy[0].cpu().numpy())

            # Рисуем
            cv2.rectangle(img, (x1,y1),(x2,y2), (0,255,0), 2)
            cv2.putText(img, name_ru, (x1, y1-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

            counts[name_en] += 1

        cv2.imwrite(res_path, img)
        people, cars = counts['person'], counts['car']

    # 5) Ветка: GIF
    elif ext == 'gif':
        frames    = imageio.mimread(src_path)
        processed = []
        counts    = {'person': set(), 'car': set()}

        for frame in frames:
            img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            det = yolo.track(img, classes=[0,2], tracker='bytetrack.yaml', verbose=False)[0]

            for box in det.boxes:
                cls       = int(box.cls.cpu().numpy())
                name_en   = yolo.names[cls]
                name_ru   = CLASS_RU.get(name_en, name_en)
                obj_id    = getattr(box, 'id', None)
                if obj_id is not None:
                    obj_id = int(obj_id.cpu().numpy())
                    if obj_id not in id_map:
                        id_map[obj_id] = next_label; next_label += 1
                    label = f"{name_ru} #{id_map[obj_id]}"
                    counts[name_en].add(obj_id)
                else:
                    label = name_ru

                x1,y1,x2,y2 = map(int, box.xyxy[0].cpu().numpy())
                cv2.rectangle(img, (x1,y1),(x2,y2), (0,255,0), 2)
                cv2.putText(img, label, (x1, y1-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

            footer = f"People: {len(counts['person'])}  Cars: {len(counts['car'])}"
            cv2.putText(img, footer, (10,30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

            processed.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        imageio.mimsave(res_path, processed, fps=10)
        people, cars = len(counts['person']), len(counts['car'])

    # 6) Ветка: видео
    else:
        cap    = cv2.VideoCapture(src_path)
        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        fps    = cap.get(cv2.CAP_PROP_FPS)
        w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        out    = cv2.VideoWriter(res_path, fourcc, fps, (w,h))
        counts = {'person': set(), 'car': set()}

        while True:
            ret, frame = cap.read()
            if not ret: break

            det = yolo.track(frame, classes=[0,2],
                             tracker='bytetrack.yaml', verbose=False)[0]

            for box in det.boxes:
                cls       = int(box.cls.cpu().numpy())
                name_en   = yolo.names[cls]
                name_ru   = CLASS_RU.get(name_en, name_en)
                raw_id    = getattr(box, 'id', None)

                if raw_id is not None:
                    obj_id = int(raw_id.cpu().numpy())
                    if obj_id not in id_map:
                        id_map[obj_id] = next_label; next_label += 1
                    label = f"{name_ru} #{id_map[obj_id]}"
                    counts[name_en].add(obj_id)
                else:
                    label = name_ru

                x1,y1,x2,y2 = map(int, box.xyxy[0].cpu().numpy())
                cv2.rectangle(frame, (x1,y1),(x2,y2), (0,255,0), 2)
                cv2.putText(frame, label, (x1, y1-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

            footer = f"People: {len(counts['person'])}  Cars: {len(counts['car'])}"
            cv2.putText(frame, footer, (10,30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

            out.write(frame)

        cap.release()
        out.release()
        people, cars = len(counts['person']), len(counts['car'])

    # 7) Рендерим итоговую страницу
    return render_template(
        'result.html',
        url= os.path.basename(res_path),
        people=people,
        cars=cars
    )
