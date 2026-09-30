import React from 'react';
import ScheduleWidget from '../components/ScheduleWidget';
import SectionIcon from '../components/SectionIcon';
import { useAuth } from '../context/AuthContext';

// The full timetable: any group, teacher or room, by day or week
const Schedule = () => {
  const { user } = useAuth();
  const ownGroup = user?.group ? { id: user.groupId || null, name: user.group } : null;

  return (
    <div className="container schedule-page">
      <header className="page-header">
        <div className="page-heading">
          <SectionIcon section="schedule" size="lg" />
          <div>
            <h1>Расписание</h1>
            <p className="page-subtitle">Пары любой группы, преподавателя или аудитории из ЭИОС КГУ.</p>
          </div>
        </div>
      </header>
      <ScheduleWidget ownGroup={ownGroup} titleHidden />
    </div>
  );
};

export default Schedule;
