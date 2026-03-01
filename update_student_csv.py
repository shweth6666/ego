import csv

def update_passwords():
    students = []
    with open('students.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # New password is First Name + 123 (no spaces)
            first_name = row['name'].strip().split(' ')[0]
            row['password'] = first_name + "123"
            students.append(row)
            
    keys = students[0].keys()
    with open('students.csv', 'w', newline='') as f:
        dict_writer = csv.DictWriter(f, keys)
        dict_writer.writeheader()
        dict_writer.writerows(students)
    print("Updated students.csv with new passwords.")

if __name__ == "__main__":
    update_passwords()
