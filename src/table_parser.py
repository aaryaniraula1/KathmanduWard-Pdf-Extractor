from src.ocr_reader import ocr_cell
from src.text_cleaner import clean_text


COLUMN_COUNT = 6


def get_native_text(page, cell_bbox) -> str:
    if cell_bbox is None:
        return ""

    text = page.get_text(
        "text",
        clip=cell_bbox,
    )

    return clean_text(text)


def append_text(existing: str, new_text: str) -> str:
    if not new_text:
        return existing

    if not existing:
        return new_text

    return f"{existing}\n{new_text}"


def extract_page_rows(page) -> list[dict]:
    table_finder = page.find_tables()
    rows = []

    for table in table_finder.tables:
        for row_index, table_row in enumerate(table.rows):

            # Skip repeated table header.
            if row_index == 0:
                continue

            cells = table_row.cells

            if len(cells) != COLUMN_COUNT:
                continue

            # Serial number is reliable from native PDF text.
            service_no = get_native_text(
                page,
                cells[0],
            )

            # OCR gives better Nepali readability.
            service = clean_text(
                ocr_cell(
                    page,
                    cells[1],
                    language="nep",
                )
            )

            # This column can contain URLs / English text.
            required_documents = clean_text(
                ocr_cell(
                    page,
                    cells[2],
                    language="nep+eng",
                )
            )

            # Keep fee from native PDF layer because
            # OCR can misread important numeric values.
            fee = get_native_text(
                page,
                cells[3],
            )

            processing_time = clean_text(
                ocr_cell(
                    page,
                    cells[4],
                    language="nep",
                )
            )

            responsible_person = clean_text(
                ocr_cell(
                    page,
                    cells[5],
                    language="nep",
                )
            )

            if not any(
                [
                    service_no,
                    service,
                    required_documents,
                    fee,
                    processing_time,
                    responsible_person,
                ]
            ):
                continue

            rows.append(
                {
                    "service_no": service_no,
                    "service": service,
                    "required_documents": required_documents,
                    "fee": fee,
                    "processing_time": processing_time,
                    "responsible_person": responsible_person,
                }
            )

    return rows


def parse_services(document) -> list[dict]:
    services = []
    current_service = None

    total_pages = len(document)

    for page_index, page in enumerate(document):
        print(
            f"Processing page "
            f"{page_index + 1}/{total_pages}"
        )

        rows = extract_page_rows(page)

        for row in rows:
            service_no = row["service_no"]

            # New serial number = new service.
            if service_no:
                if current_service:
                    services.append(
                        current_service
                    )

                current_service = {
                    "service_no": service_no,
                    "service": row["service"],
                    "required_documents": row[
                        "required_documents"
                    ],
                    "fee": row["fee"],
                    "processing_time": row[
                        "processing_time"
                    ],
                    "responsible_person": row[
                        "responsible_person"
                    ],
                    "start_page": page_index + 1,
                    "end_page": page_index + 1,
                }

                continue

            # Blank serial = continuation of previous service.
            if current_service is None:
                continue

            current_service[
                "service"
            ] = append_text(
                current_service["service"],
                row["service"],
            )

            current_service[
                "required_documents"
            ] = append_text(
                current_service[
                    "required_documents"
                ],
                row["required_documents"],
            )

            current_service[
                "fee"
            ] = append_text(
                current_service["fee"],
                row["fee"],
            )

            current_service[
                "processing_time"
            ] = append_text(
                current_service[
                    "processing_time"
                ],
                row["processing_time"],
            )

            current_service[
                "responsible_person"
            ] = append_text(
                current_service[
                    "responsible_person"
                ],
                row["responsible_person"],
            )

            current_service[
                "end_page"
            ] = page_index + 1

    if current_service:
        services.append(
            current_service
        )

    return services